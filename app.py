"""Flask routes and Socket.IO handlers for the Prisoner's Dilemma lobby.

All game state lives in `game.py`. Socket handlers identify the player by the socket that sent
the event (`request.sid`), never by data the browser sends, and validate every payload.
"""

import logging
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session
from flask_socketio import SocketIO

from game import LEADERBOARD_MIN_GAMES, GameError, GameState, Match, Player

load_dotenv()  # pick up SECRET_KEY / DEBUG / HOST / PORT from a local .env, if present
log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 30


def env_flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def load_secret_key(environ=os.environ) -> str:
    key = environ.get("SECRET_KEY")
    if key:
        return key
    # Fine for local play: sessions just don't survive a server restart.
    log.warning("SECRET_KEY is not set; using a random key for this run")
    return secrets.token_hex(32)


def run_options(environ=os.environ) -> dict:
    """Keyword arguments for socketio.run(). Debug is opt-in: on 0.0.0.0 the Werkzeug debugger
    would let anyone on the network run code on this machine."""
    return {
        "host": environ.get("HOST", "0.0.0.0"),
        "port": int(environ.get("PORT", "5000")),
        "debug": env_flag(environ.get("DEBUG")),
        # Flask-SocketIO refuses to start Werkzeug's dev server without debug unless told to.
        "allow_unsafe_werkzeug": True,
    }


app = Flask(__name__)
app.config["SECRET_KEY"] = load_secret_key()
# How long a dropped connection may take to come back (a page reload, a network blip) before the
# player's match is ended and the name is freed. 0 ends it immediately.
app.config["DISCONNECT_GRACE_SECONDS"] = float(os.environ.get("DISCONNECT_GRACE_SECONDS", "10"))
socketio = SocketIO(app)
state = GameState()


# --- helpers -------------------------------------------------------------------


def broadcast_user_list():
    socketio.emit("update_user_list", state.status())


def show_lobby(player: Player):
    if not player.online:
        return  # emitting to=None would broadcast to everyone
    js = {"username": player.name, "score": player.average, "user_list": state.status()}
    socketio.emit("lobby_page", js, to=player.sid)


def finish_match(match: Match):
    """End a match for whatever reason; both players still online go back to the lobby."""
    players = state.end_match(match)
    online = [p for p in players if p.online]
    for p in online:
        socketio.emit("game_end", to=p.sid)
    broadcast_user_list()
    for p in online:
        show_lobby(p)


def take_offline(player: Player):
    """Logout or lost connection: free the name and end any match so the opponent isn't stuck."""
    state.unbind(player)
    player.reconnect_token = None
    if player.match is not None:
        finish_match(player.match)  # also sends the updated user list
    else:
        broadcast_user_list()
    state.forget_if_unplayed(player)


def current_player() -> Player | None:
    return state.player_by_sid(request.sid)


def expire_after_grace(name: str, token: object, seconds: float):
    """Background task: take the player offline unless they reconnected in the meantime."""
    socketio.sleep(seconds)
    with state.lock:
        player = state.get(name)
        if player is not None and player.reconnect_token is token:
            take_offline(player)


# --- HTTP routes ---------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    js = request.get_json(silent=True)
    if not isinstance(js, dict):
        return "Invalid request.", 400
    name = js.get("username")
    if not isinstance(name, str) or not name.strip():
        return "Please enter a username!", 400
    name = name.strip()
    if len(name) > MAX_NAME_LENGTH:
        return f"Username must be at most {MAX_NAME_LENGTH} characters.", 400

    with state.lock:
        existing = state.get(name)
        if existing is not None and existing.reserved:
            return "Username already taken!", 409
        player = state.get_or_create(name)
        session["username"] = name
        # The browser sends its socket id so the name is reserved straight away. Only accept it
        # if it is a live socket that nobody owns; otherwise the page reload that follows login
        # binds the real socket in `initialize`.
        sid = js.get("sid")
        if isinstance(sid, str) and sid in state.connected and state.player_by_sid(sid) is None:
            state.bind(player, sid)
        broadcast_user_list()
        return {"username": name, "score": player.average, "user_list": state.status()}, 200


@app.route("/logout", methods=["GET", "POST"])
def logout():
    name = session.pop("username", None)
    with state.lock:
        player = state.get(name)
        if player is not None:
            take_offline(player)
    return redirect("/")


@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    with state.lock:
        rows = state.leaderboard()
    return render_template("leaderboard.html", leaderboard=rows, min_games=LEADERBOARD_MIN_GAMES)


# --- Socket.IO events ------------------------------------------------------------


@socketio.on("connect")
def on_connect():
    with state.lock:
        state.connected.add(request.sid)


@socketio.on("disconnect")
def on_disconnect():
    with state.lock:
        state.connected.discard(request.sid)
        player = current_player()
        if player is None:
            return
        grace = app.config["DISCONNECT_GRACE_SECONDS"]
        if grace <= 0:
            take_offline(player)
            return
        # Keep the name and match for a moment: a page reload reconnects within a second.
        state.unbind(player)
        token = object()
        player.reconnect_token = token
        socketio.start_background_task(expire_after_grace, player.name, token, grace)


@socketio.on("initialize")
def initialize():
    """Sent by every page load: show the login, lobby or game page for this browser session."""
    with state.lock:
        name = session.get("username")
        player = state.get(name)
        if player is None and name:
            # Logged in earlier but forgotten (e.g. the page reload right after login).
            player = state.get_or_create(name)
        if player is None:
            socketio.emit("login_page", request.sid, to=request.sid)
            return

        # The newest tab of this session takes over; the older tab is sent back to the login.
        replaced = state.bind(player, request.sid)
        if replaced is not None:
            socketio.emit("login_page", replaced, to=replaced)
        broadcast_user_list()

        match = player.match
        if match is None:
            show_lobby(player)
            return
        opponent = match.opponent(player)
        js = {
            "username": player.name,
            "opponent": opponent.name,
            "your_score": match.round_scores[player.name],
            "opponent_score": match.round_scores[opponent.name],
            "decision": match.decisions[player.name],
        }
        socketio.emit("game_page", js, to=request.sid)


@socketio.on("issue_challenge")
def handle_challenge(js):
    with state.lock:
        challenger = current_player()
        if challenger is None:
            return
        receiver_name = js.get("receiver") if isinstance(js, dict) else None
        if not isinstance(receiver_name, str):
            socketio.emit("challenge_failed", "Invalid challenge.", to=request.sid)
            return
        try:
            match = state.challenge(challenger, receiver_name)
        except GameError as e:
            socketio.emit("challenge_failed", str(e), to=request.sid)
            return
        # Challenges are accepted automatically (game design).
        receiver = match.opponent(challenger)
        broadcast_user_list()
        socketio.emit("challenge_issued", receiver.name, to=challenger.sid)
        socketio.emit("challenge_accepted", challenger.name, to=receiver.sid)


@socketio.on("submit_option")
def handle_decision(option):
    with state.lock:
        player = current_player()
        if player is None or player.match is None:
            return
        match = player.match
        try:
            result = match.submit(player, option)
        except GameError as e:
            log.info("refused move from %s: %s", player.name, e)
            return
        if result is None:
            return  # waiting for the opponent

        for p in match.players:
            if not p.online:
                continue
            other = match.opponent(p)
            js = {
                "your_option": result.options[p.name],
                "enemy_option": result.options[other.name],
                "your_score": result.scores[p.name],
                "enemy_score": result.scores[other.name],
            }
            socketio.emit("game_result", js, to=p.sid)
        if match.finished:
            finish_match(match)


@socketio.on("terminate_game")
def terminate_game():
    with state.lock:
        player = current_player()
        if player is None:
            return
        if player.match is not None:
            finish_match(player.match)
        else:
            show_lobby(player)  # nothing to leave; just make sure the page shows the lobby


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    socketio.run(app, **run_options())
