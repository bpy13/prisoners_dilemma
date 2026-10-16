"""Unit tests for the game model (no Flask involved)."""

import pytest

from game import MAX_ROUNDS, MIN_ROUNDS, GameError, GameState, compute_score


@pytest.mark.parametrize(
    ("mine", "theirs", "expected"),
    [
        ("split", "split", (3, 3)),
        ("split", "steal", (0, 5)),
        ("steal", "split", (5, 0)),
        ("steal", "steal", (1, 1)),
    ],
)
def test_payoff_table(mine, theirs, expected):
    assert compute_score(mine, theirs) == expected


def test_compute_score_rejects_unknown_option():
    with pytest.raises(GameError):
        compute_score("split", "cheat")


def online_pair(state, rounds=5):
    a = state.get_or_create("alice")
    b = state.get_or_create("bob")
    state.bind(a, "sid-a")
    state.bind(b, "sid-b")
    match = state.start_match(a, b, rounds=rounds)
    return a, b, match


def test_round_waits_for_both_decisions_then_scores():
    state = GameState()
    a, b, match = online_pair(state)
    assert match.submit(a, "steal") is None
    result = match.submit(b, "split")
    assert result.scores == {"alice": 5, "bob": 0}
    assert result.options == {"alice": "steal", "bob": "split"}
    assert match.rounds_left == 4
    assert match.round_scores == {"alice": [5], "bob": [0]}
    assert match.decisions == {"alice": None, "bob": None}
    assert (a.total_score, a.rounds_played) == (5, 1)
    assert (b.total_score, b.rounds_played) == (0, 1)


def test_second_decision_in_same_round_is_refused():
    state = GameState()
    a, _, match = online_pair(state)
    match.submit(a, "split")
    with pytest.raises(GameError):
        match.submit(a, "steal")


def test_invalid_option_is_refused_and_not_recorded():
    state = GameState()
    a, _, match = online_pair(state)
    with pytest.raises(GameError):
        match.submit(a, "cheat")
    assert match.decisions["alice"] is None


def test_full_match_finishes_and_counts_a_game():
    state = GameState()
    a, b, match = online_pair(state, rounds=5)
    for _ in range(5):
        match.submit(a, "split")
        match.submit(b, "split")
    assert match.finished
    state.end_match(match)
    assert a.match is None and b.match is None
    assert a.games_played == b.games_played == 1
    assert a.average == 3.0


def test_random_round_count_in_range():
    state = GameState()
    a = state.get_or_create("alice")
    b = state.get_or_create("bob")
    state.bind(a, "sid-a")
    state.bind(b, "sid-b")
    seen = set()
    for _ in range(200):
        match = state.start_match(a, b)
        seen.add(match.rounds_left)
        state.end_match(match)
    assert seen == set(range(MIN_ROUNDS, MAX_ROUNDS + 1))


@pytest.mark.parametrize("case", ["self", "unknown", "offline", "receiver_busy", "challenger_busy"])
def test_invalid_challenges_are_refused(case):
    state = GameState()
    a = state.get_or_create("alice")
    b = state.get_or_create("bob")
    c = state.get_or_create("carol")
    state.bind(a, "sid-a")
    state.bind(b, "sid-b")
    state.bind(c, "sid-c")
    receiver = {"self": "alice", "unknown": "zed", "offline": "dave"}.get(case, "bob")
    state.get_or_create("dave")  # exists but never bound to a socket
    if case == "receiver_busy":
        state.start_match(b, c, rounds=5)
    if case == "challenger_busy":
        state.start_match(a, c, rounds=5)
    with pytest.raises(GameError):
        state.challenge(a, receiver)


def test_status_lists_only_online_players():
    state = GameState()
    a, b, _ = online_pair(state)
    state.get_or_create("dave")  # offline
    assert state.status() == {"alice": "bob", "bob": "alice"}


def test_bind_refuses_a_socket_owned_by_someone_else():
    state = GameState()
    a, b = state.get_or_create("alice"), state.get_or_create("bob")
    state.bind(a, "sid-a")
    with pytest.raises(GameError):
        state.bind(b, "sid-a")
    assert a.sid == "sid-a" and state.player_by_sid("sid-a") is a and not b.online


def test_unbind_frees_the_name_and_sid():
    state = GameState()
    a = state.get_or_create("alice")
    state.bind(a, "sid-a")
    state.unbind(a)
    assert not a.online
    assert state.player_by_sid("sid-a") is None


def test_leaderboard_sorts_numerically_and_needs_seven_games():
    state = GameState()
    for name, total, rounds, games in [
        ("high", 20, 2, 7),  # average 10.0
        ("mid", 19, 2, 7),  # average 9.5; sorted as text "9.5" would beat "10.0"
        ("low", 1, 1, 9),
        ("newbie", 50, 10, 6),  # under the 7-game threshold
    ]:
        p = state.get_or_create(name)
        p.total_score, p.rounds_played, p.games_played = total, rounds, games
    assert state.leaderboard() == [("high", 10.0), ("mid", 9.5), ("low", 1.0)]


def test_average_is_zero_before_any_round():
    state = GameState()
    assert state.get_or_create("alice").average == 0
