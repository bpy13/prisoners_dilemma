# Plan: robustness pass (2026-10-16)

**Goal:** fix the code-review findings so the game survives closed tabs, mid-game logouts and
bad input, without changing the game design.

**Approach:** replace the 8 parallel `data[...]` dicts and the `sid` dict with a `Player`
dataclass and a `Match` object shared by both players (in a new `game.py`). Socket handlers
find the player by `request.sid`, validate every event, and tear matches down through one
function used by leave, logout and disconnect. Add pytest tests (Flask-SocketIO test client)
and ruff. Built by one agent in this session (no per-phase helpers, as instructed).

**Constraints (from `docs/decisions.md`):**
- Kept as-is: payoffs 3/3, 0/5, 5/0, 1/1; 5–9 random rounds; challenges are auto-accepted;
  leaderboard is average score per round, shown only for players with 7+ games.
- Debug mode is opt-in through `DEBUG=1`; default off.
- `SECRET_KEY` comes from the environment or `.env`; random fallback; `.env` is git-ignored.
- Client protocol (event names and payloads) stays compatible with `static/socketIO.js`.

**Acceptance criteria**
1. Closing a tab frees the username and returns the opponent to the lobby.
2. Logging out mid-game ends the match cleanly; the opponent's next action doesn't crash.
3. Invalid challenges (self, unknown, offline, either side busy), invalid moves and moves or
   leaves without a match are refused without a server error. Login does not bind an
   arbitrary client-supplied sid.
4. Leaderboard sorts by the numeric average.
5. Debug off by default; SECRET_KEY from env; `.env.example` present; no secret committed.
6. README documents setup, env vars, tests, auto-accept and the 7-game threshold.
7. Tests and ruff pass; app launched and main flow checked with two socket clients.

## Phase 1 – Setup and refactor (single phase)

- [x] **Task 1: Project docs and environment**
  - Files: create `CLAUDE.md`, `docs/decisions.md`, `docs/open-items.md`, this plan,
    `environment.yml`, `requirements-dev.txt`, `pyproject.toml` (ruff + pytest config)
  - Done when: `conda run -n prisoners_dilemma python -m pytest --version` and
    `ruff --version` both print a version.
- [x] **Task 2: Scoring and game model with tests first**
  - Files: create `game.py` (`compute_score`, `Player`, `Match`, `GameState`),
    `tests/test_game.py`
  - Done when: `python -m pytest tests/test_game.py` passes (payoff table, round flow,
    average, leaderboard ordering numeric: 10.0 above 9.5).
- [x] **Task 3: Rewrite socket handlers and routes on the new model**
  - Files: modify `app.py`; create `tests/test_app.py`
  - Done when: `python -m pytest` passes, covering a full match through the SocketIO test
    client, invalid moves/challenges, disconnect and logout mid-game, login with a bogus sid,
    leaderboard page order.
  - Change during build: a disconnect waits `DISCONNECT_GRACE_SECONDS` (default 10) before
    ending the match and freeing the name, so the page reload after login, or a refresh
    mid-game, doesn't end the game. The name stays reserved during that time.
  - Notes: `connect`/`disconnect` handlers track live sockets; `initialize` binds the session's
    player to `request.sid` (the newest tab wins; the old tab gets `login_page`); login accepts
    the client sid only if it is a live socket not bound to anyone, otherwise it logs in
    unbound and the reload's `initialize` binds it. Lock `state.lock` around state changes.
- [x] **Task 4: Config: debug, secret key, host/port**
  - Files: modify `app.py`; create `.env.example`; modify `.gitignore`
  - Done when: a test asserts debug defaults off and SECRET_KEY is read from the env; the app
    starts with no `.env` (checked by launching it).
  - Notes: env vars `SECRET_KEY`, `DEBUG` (1/true/yes), `HOST` (default 0.0.0.0), `PORT`
    (default 5000). Load `.env` with python-dotenv. `allow_unsafe_werkzeug=True` is needed to
    run the dev server with debug off.
- [x] **Task 5: Client and template touch-ups**
  - Files: modify `static/socketIO.js` (alert on `challenge_failed`),
    `templates/leaderboard.html` (cdnjs Bootstrap URL, formatted score)
  - Done when: two scripted socket clients complete the main flow against the running app and
    `/leaderboard` renders.
- [x] **Task 6: Repo hygiene**
  - Files: `git rm --cached static/.DS_Store`; `.gitignore` gets `**/.DS_Store`, `.env`,
    caches; shrink `png/*.png` to 800px wide
  - Done when: `git ls-files` shows no `.DS_Store`; png sizes drop and the images still look
    right when opened.
- [ ] **Task 7: README and requirements**
  - Files: modify `README.md`, `requirements.txt`
  - Done when: README covers setup (conda and pip), env vars, running, tests, lint, rules
    including auto-accept and the 7-game threshold; commands in it were run.
- [ ] **Task 8: End of run** – pre-release review, fix in-scope findings, wrap-up, ship.
