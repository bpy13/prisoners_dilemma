"""Integration tests: browsers simulated with Flask's HTTP client plus Flask-SocketIO's test
client, following the same steps static/socketIO.js takes."""

import time

import pytest

import app as app_module
import game
from app import app, load_secret_key, run_options, socketio, state


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    state.reset()
    app.config["TESTING"] = True
    app.config["DISCONNECT_GRACE_SECONDS"] = 0  # tests of the grace period set their own
    monkeypatch.setattr(game.random, "randint", lambda lo, hi: 5)  # every match: 5 rounds
    yield
    state.reset()


class Browser:
    """One browser tab: a cookie jar (HTTP client) and a socket that share the session."""

    def __init__(self):
        self.http = app.test_client()
        self.sock = None
        self.sid = None  # what the client stores from 'login_page' and sends with /login
        self.open_page()

    def open_page(self):
        """What loading index.html does: connect and send 'initialize'."""
        self.sock = socketio.test_client(app, flask_test_client=self.http)
        self.sock.emit("initialize")
        self.pending = self.sock.get_received()  # kept for the next events() call
        pages = [e["args"] for e in self.pending if e["name"] == "login_page"]
        if pages:
            self.sid = pages[-1][0]

    def reload(self):
        self.sock.disconnect()
        self.open_page()

    def events(self, name=None):
        """Events received since the last call (all, or only those called `name`)."""
        received = self.pending + self.sock.get_received()
        self.pending = []
        if name is None:
            return received
        return [e["args"] for e in received if e["name"] == name]

    def login(self, username):
        resp = self.http.post("/login", json={"username": username, "sid": self.sid})
        if resp.status_code == 200:
            self.reload()  # the client reloads after login so the socket sees the session
        return resp


def two_players():
    alice, bob = Browser(), Browser()
    assert alice.login("alice").status_code == 200
    assert bob.login("bob").status_code == 200
    alice.events(), bob.events()
    return alice, bob


def start_match(alice, bob):
    alice.sock.emit("issue_challenge", {"receiver": "bob"})
    assert alice.events("challenge_issued") == [["bob"]]
    assert bob.events("challenge_accepted") == [["alice"]]


def test_login_shows_lobby_with_other_players():
    alice = Browser()
    alice.login("alice")
    bob = Browser()
    resp = bob.login("bob")
    assert resp.get_json()["user_list"] == {"alice": "", "bob": ""}
    alice.reload()
    lobby = alice.events("lobby_page")[-1][0]
    assert lobby == {"username": "alice", "score": 0, "user_list": {"alice": "", "bob": ""}}


def test_full_match_scores_and_returns_to_lobby():
    alice, bob = two_players()
    start_match(alice, bob)
    for i in range(5):
        alice.sock.emit("submit_option", "steal")
        assert bob.events("game_result") == []  # waits for both
        bob.sock.emit("submit_option", "split")
        assert alice.events("game_result") == [
            [{"your_option": "steal", "enemy_option": "split", "your_score": 5, "enemy_score": 0}]
        ]
        received = bob.events()
        names = [e["name"] for e in received]
        assert names[0] == "game_result"
        assert received[0]["args"][0]["your_score"] == 0
        if i < 4:
            assert "game_end" not in names
    assert "game_end" in names and names[-1] == "lobby_page"
    assert received[-1]["args"][0]["score"] == 0
    a, b = state.get("alice"), state.get("bob")
    assert (a.average, a.games_played, a.match) == (5.0, 1, None)
    assert (b.average, b.games_played, b.match) == (0, 1, None)


def test_reload_mid_game_restores_game_page():
    alice, bob = two_players()
    app.config["DISCONNECT_GRACE_SECONDS"] = 5
    start_match(alice, bob)
    alice.sock.emit("submit_option", "split")
    bob.sock.emit("submit_option", "split")
    alice.sock.emit("submit_option", "steal")
    alice.reload()
    page = alice.events("game_page")[-1][0]
    assert page == {
        "username": "alice",
        "opponent": "bob",
        "your_score": [3],
        "opponent_score": [3],
        "decision": "steal",
    }
    assert "game_end" not in [e["name"] for e in bob.events()]


@pytest.mark.parametrize(
    ("receiver", "setup"),
    [("alice", None), ("nobody", None), ("bob", "bob_busy"), ("bob", "alice_busy"), (None, None)],
)
def test_invalid_challenges_are_refused(receiver, setup):
    alice, bob = two_players()
    carol = Browser()
    carol.login("carol")
    if setup == "bob_busy":
        bob.sock.emit("issue_challenge", {"receiver": "carol"})
    if setup == "alice_busy":
        alice.sock.emit("issue_challenge", {"receiver": "carol"})
    alice.events(), bob.events()
    alice.sock.emit("issue_challenge", {"receiver": receiver})
    failed = alice.events("challenge_failed")
    assert len(failed) == 1 and isinstance(failed[0][0], str)
    assert bob.events("challenge_accepted") == []


def test_challenge_with_garbage_payload_is_refused():
    alice, _ = two_players()
    alice.sock.emit("issue_challenge", "bob")
    assert len(alice.events("challenge_failed")) == 1


def test_offline_player_with_history_cannot_be_challenged():
    alice, bob = two_players()
    state.get("bob").games_played = 3  # has history, so is kept after logout
    bob.http.post("/logout")
    alice.events()
    alice.sock.emit("issue_challenge", {"receiver": "bob"})
    assert len(alice.events("challenge_failed")) == 1


def test_invalid_moves_are_ignored():
    alice, bob = two_players()
    alice.sock.emit("submit_option", "split")  # no match yet: ignored, no crash
    start_match(alice, bob)
    for bad in ["cheat", "", None, {"x": 1}, ["split"]]:
        alice.sock.emit("submit_option", bad)
    bob.sock.emit("submit_option", "split")
    assert alice.events("game_result") == []  # alice's bad moves were not recorded
    alice.sock.emit("submit_option", "split")
    assert len(alice.events("game_result")) == 1
    bob.sock.emit("submit_option", "steal")
    bob.sock.emit("submit_option", "split")  # second move in the same round: ignored
    assert state.get("bob").match.decisions["bob"] == "steal"


def test_terminate_without_match_just_shows_lobby():
    alice, _ = two_players()
    alice.sock.emit("terminate_game")
    assert len(alice.events("lobby_page")) == 1


def test_events_from_unknown_socket_are_ignored():
    stranger = Browser()  # connected, never logged in
    stranger.events()  # drop the login_page it was shown
    for event, arg in [("issue_challenge", {"receiver": "x"}), ("submit_option", "split")]:
        stranger.sock.emit(event, arg)
    stranger.sock.emit("terminate_game")
    assert stranger.events() == []


def test_wrong_number_of_arguments_is_ignored():
    alice, bob = two_players()
    alice.sock.emit("issue_challenge")
    assert len(alice.events("challenge_failed")) == 1
    start_match(alice, bob)
    alice.sock.emit("submit_option")
    alice.sock.emit("submit_option", "split", "steal")
    assert state.get("alice").match.decisions["alice"] is None
    alice.sock.emit("initialize", "extra")
    alice.sock.emit("terminate_game", "extra")
    assert "game_end" in [e["name"] for e in bob.events()]


def test_old_cookie_cannot_take_back_a_name_someone_else_holds():
    first = Browser()
    first.login("bob")
    first.sock.disconnect()  # tab closed: name freed (grace period 0 in tests)
    second, dave = Browser(), Browser()
    assert second.login("bob").status_code == 200
    dave.login("dave")
    second.sock.emit("issue_challenge", {"receiver": "dave"})
    first.open_page()  # the first browser comes back with its old cookie
    assert len(first.events("login_page")) == 1
    assert first.events("game_page") == []
    first.http.post("/logout")  # must not end the new bob's game
    assert state.get("bob").match is not None and state.get("bob").online


def test_leave_game_returns_both_to_lobby():
    alice, bob = two_players()
    start_match(alice, bob)
    alice.sock.emit("submit_option", "split")
    bob.sock.emit("submit_option", "split")
    bob.sock.emit("terminate_game")
    for browser in (alice, bob):
        names = [e["name"] for e in browser.events()]
        assert "game_end" in names and names[-1] == "lobby_page"
    assert state.get("alice").games_played == 1


def test_disconnect_mid_game_frees_name_and_opponent():
    alice, bob = two_players()
    start_match(alice, bob)
    alice.sock.disconnect()  # tab closed
    names = [e["name"] for e in bob.events()]
    assert "game_end" in names and names[-1] == "lobby_page"
    assert state.get("bob").match is None
    bob.sock.emit("submit_option", "split")  # used to raise KeyError; now ignored
    again = Browser()
    assert again.login("alice").status_code == 200  # name no longer reserved


def test_disconnect_waits_for_grace_period_then_ends_match():
    alice, bob = two_players()
    app.config["DISCONNECT_GRACE_SECONDS"] = 0.3
    start_match(alice, bob)
    alice.sock.disconnect()
    assert bob.events("game_end") == []
    other = Browser()
    assert other.login("alice").status_code == 409  # still reserved during the grace period
    time.sleep(0.6)
    assert len(bob.events("game_end")) == 1
    assert state.get("bob").match is None
    assert other.login("alice").status_code == 200


def test_logout_mid_game_ends_match_for_opponent():
    alice, bob = two_players()
    start_match(alice, bob)
    resp = alice.http.post("/logout")
    assert resp.status_code == 302
    names = [e["name"] for e in bob.events()]
    assert "game_end" in names and names[-1] == "lobby_page"
    bob.sock.emit("submit_option", "steal")  # must not crash
    bob.sock.emit("terminate_game")
    assert state.status() == {"bob": ""}
    assert state.get("alice").games_played == 1  # kept: has played a game


def test_logout_forgets_player_who_never_played():
    alice, _ = two_players()
    alice.http.post("/logout")
    assert state.get("alice") is None


def test_logout_without_session_redirects():
    resp = app.test_client().post("/logout")
    assert resp.status_code == 302


def test_duplicate_username_rejected_while_online():
    alice = Browser()
    alice.login("alice")
    other = Browser()
    resp = other.login("alice")
    assert resp.status_code == 409


@pytest.mark.parametrize("name", ["", "   ", None, 42, "x" * 31])
def test_bad_usernames_rejected(name):
    b = Browser()
    resp = b.http.post("/login", json={"username": name, "sid": b.sid})
    assert resp.status_code == 400


def test_login_does_not_bind_someone_elses_socket():
    _, bob = two_players()
    bob_sid = state.get("bob").sid
    mallory = Browser()
    resp = mallory.http.post("/login", json={"username": "mallory", "sid": bob_sid})
    assert resp.status_code == 200
    assert state.player_by_sid(bob_sid).name == "bob"
    assert not state.get("mallory").online
    resp = mallory.http.post("/login", json={"username": "eve", "sid": "made-up"})
    assert resp.status_code == 200 and not state.get("eve").online


def test_leaderboard_page_sorted_numerically():
    for name, total, rounds, games in [("mid", 19, 2, 7), ("high", 20, 2, 7), ("new", 9, 1, 6)]:
        p = state.get_or_create(name)
        p.total_score, p.rounds_played, p.games_played = total, rounds, games
    html = app.test_client().get("/leaderboard").get_data(as_text=True)
    assert html.index("high") < html.index("mid")
    assert "10.00" in html and "9.50" in html
    assert "new" not in html.split("<tbody>")[1]


def test_debug_is_off_unless_enabled():
    assert run_options({})["debug"] is False
    assert run_options({"DEBUG": "0"})["debug"] is False
    assert run_options({"DEBUG": "1"})["debug"] is True
    assert run_options({"HOST": "127.0.0.1", "PORT": "8000"})["port"] == 8000


def test_secret_key_from_environment_or_random():
    assert load_secret_key({"SECRET_KEY": "from-env"}) == "from-env"
    a, b = load_secret_key({}), load_secret_key({})
    assert a != b and len(a) == 64
    assert app_module.app.config["SECRET_KEY"] != "prisoners_dilemma"
