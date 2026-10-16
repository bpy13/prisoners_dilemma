# Prisoner's Dilemma – notes for Claude

A small Flask + Flask-SocketIO web game: players pick a username, see a lobby of online
players, challenge each other to a 5–9 round Prisoner's Dilemma match, and appear on a
leaderboard once they have played 7 games. It's a hobby/demo project in a public GitHub repo;
users are friends playing on the same network.

Read these before substantial changes:

- `docs/decisions.md` – what was decided and why (don't re-litigate without a reason)
- `docs/open-items.md` – pending work and questions waiting on the user
- `docs/plans/` – the latest plan
- `README.md` – user-facing setup and commands

## Environment
- Install: `conda env create -f environment.yml; conda activate prisoners_dilemma`
- Run: `python app.py` (http://localhost:5000)
- Tests: `python -m pytest`
- Lint: `ruff check .`

## Project rules
- Game design is fixed: payoffs 3/3, 0/5, 5/0, 1/1; 5–9 random rounds; challenges are
  auto-accepted; leaderboard = average score per round, players with 7+ games only. Don't
  change these without the user asking.
- The client protocol (socket event names and payloads used by `static/socketIO.js`) is a
  contract; change server and JS together.
- Never commit `.env` or a real `SECRET_KEY`. Debug mode stays opt-in (`DEBUG=1`).
- The repo is public: no client names or personal data.

## Conventions
- All game state lives in `game.py` (`Player`, `Match`, `GameState`); `app.py` only holds the
  Flask routes and socket handlers, which look players up by `request.sid` and hold
  `state.lock` while they change state.
- Every socket event validates its input server-side; the browser is never trusted.
