"""Game state for the Prisoner's Dilemma lobby, kept in memory and independent of Flask.

A `Player` lives for as long as the server runs (so returning players keep their stats).
A `Match` is shared by its two players and holds everything about the game in progress.
`GameState` owns all players and the socket-id lookup; callers hold `GameState.lock` while
they read or change it, because Flask-SocketIO runs handlers on several threads.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field

SPLIT = "split"
STEAL = "steal"
OPTIONS = (SPLIT, STEAL)

# (my points, their points) for (my option, their option)
PAYOFFS = {
    (SPLIT, SPLIT): (3, 3),
    (SPLIT, STEAL): (0, 5),
    (STEAL, SPLIT): (5, 0),
    (STEAL, STEAL): (1, 1),
}

MIN_ROUNDS = 5
MAX_ROUNDS = 9
LEADERBOARD_MIN_GAMES = 7


class GameError(ValueError):
    """A request that breaks the rules (bad option, unavailable opponent, ...)."""


def compute_score(mine: str, theirs: str) -> tuple[int, int]:
    try:
        return PAYOFFS[(mine, theirs)]
    except KeyError:
        raise GameError(f"unknown option: {mine!r} / {theirs!r}") from None


@dataclass(eq=False)
class Player:
    name: str
    sid: str | None = None  # socket currently driving this player; None when offline
    total_score: int = 0
    rounds_played: int = 0
    games_played: int = 0
    match: Match | None = None
    # Set while a dropped connection may still come back (page reload, network blip); the
    # name stays reserved and the match stays open until the grace period runs out.
    reconnect_token: object | None = None
    # Random value from the latest login, also stored in that browser's session cookie, so an
    # old cookie can't take the name back after someone else has logged in with it.
    login_token: str | None = None

    @property
    def online(self) -> bool:
        return self.sid is not None

    @property
    def reserved(self) -> bool:
        """True while nobody else may log in with this name."""
        return self.online or self.reconnect_token is not None

    @property
    def average(self) -> float:
        """Average points per round, the number the lobby and leaderboard show."""
        if self.rounds_played == 0:
            return 0
        return round(self.total_score / self.rounds_played, 2)


@dataclass
class RoundResult:
    options: dict[str, str]
    scores: dict[str, int]


@dataclass(eq=False)
class Match:
    players: tuple[Player, Player]
    rounds_left: int
    decisions: dict[str, str | None] = field(default_factory=dict)
    round_scores: dict[str, list[int]] = field(default_factory=dict)

    def __post_init__(self):
        for p in self.players:
            self.decisions.setdefault(p.name, None)
            self.round_scores.setdefault(p.name, [])

    @property
    def finished(self) -> bool:
        return self.rounds_left <= 0

    def opponent(self, player: Player) -> Player:
        a, b = self.players
        return b if player is a else a

    def submit(self, player: Player, option: str) -> RoundResult | None:
        """Record a decision; once both players have decided, score the round and return it."""
        if option not in OPTIONS:
            raise GameError(f"invalid option: {option!r}")
        if self.finished:
            raise GameError("match already finished")
        if self.decisions[player.name] is not None:
            raise GameError("already decided this round")
        self.decisions[player.name] = option
        other = self.opponent(player)
        if self.decisions[other.name] is None:
            return None

        mine, theirs = option, self.decisions[other.name]
        my_points, their_points = compute_score(mine, theirs)
        for p, points in ((player, my_points), (other, their_points)):
            p.total_score += points
            p.rounds_played += 1
            self.round_scores[p.name].append(points)
            self.decisions[p.name] = None
        self.rounds_left -= 1
        return RoundResult(
            options={player.name: mine, other.name: theirs},
            scores={player.name: my_points, other.name: their_points},
        )


class GameState:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        self.players: dict[str, Player] = {}
        self._by_sid: dict[str, Player] = {}
        self.connected: set[str] = set()  # every live socket id, bound to a player or not

    # --- players and sockets -------------------------------------------------

    def get(self, name: str | None) -> Player | None:
        return self.players.get(name) if name else None

    def get_or_create(self, name: str) -> Player:
        if name not in self.players:
            self.players[name] = Player(name)
        return self.players[name]

    def forget_if_unplayed(self, player: Player):
        """Drop an offline player who has never played, so the name list doesn't grow forever.

        Players with history are kept for the leaderboard and get their stats back when they
        log in again with the same name.
        """
        never_played = player.rounds_played == 0 and player.games_played == 0
        if never_played and not player.reserved and player.match is None:
            self.players.pop(player.name, None)

    def player_by_sid(self, sid: str) -> Player | None:
        return self._by_sid.get(sid)

    def bind(self, player: Player, sid: str) -> str | None:
        """Attach a socket to a player. Returns the socket it replaced, if any."""
        previous_owner = self._by_sid.get(sid)
        if previous_owner is not None and previous_owner is not player:
            # Callers only bind sockets nobody owns; silently moving it would strand the other
            # player's match.
            raise GameError("socket already belongs to another player")
        old = player.sid
        if old is not None and old != sid:
            self._by_sid.pop(old, None)
        player.sid = sid
        player.reconnect_token = None
        self._by_sid[sid] = player
        return old if old != sid else None

    def unbind(self, player: Player):
        if player.sid is not None:
            self._by_sid.pop(player.sid, None)
        player.sid = None

    def status(self) -> dict[str, str]:
        """Online players -> opponent name, or '' when free. This is the client's user_list."""
        return {
            p.name: (p.match.opponent(p).name if p.match else "")
            for p in self.players.values()
            if p.online
        }

    # --- matches -------------------------------------------------------------

    def challenge(self, challenger: Player, receiver_name: str) -> Match:
        receiver = self.players.get(receiver_name)
        if receiver is None or not receiver.online:
            raise GameError("that player is not online")
        if receiver is challenger:
            raise GameError("you cannot challenge yourself")
        if challenger.match is not None:
            raise GameError("you are already in a game")
        if receiver.match is not None:
            raise GameError("that player is already in a game")
        return self.start_match(challenger, receiver)

    def start_match(self, a: Player, b: Player, rounds: int | None = None) -> Match:
        if rounds is None:
            rounds = random.randint(MIN_ROUNDS, MAX_ROUNDS)
        match = Match(players=(a, b), rounds_left=rounds)
        a.match = b.match = match
        return match

    def end_match(self, match: Match) -> tuple[Player, Player]:
        """End a match (finished or not). Rounds already scored are kept; it counts as a game."""
        for p in match.players:
            if p.match is match:
                p.match = None
                p.games_played += 1
        return match.players

    def leaderboard(self) -> list[tuple[str, float]]:
        qualified = [p for p in self.players.values() if p.games_played >= LEADERBOARD_MIN_GAMES]
        qualified.sort(key=lambda p: p.average, reverse=True)
        return [(p.name, p.average) for p in qualified]
