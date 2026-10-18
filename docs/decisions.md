# Decisions

What was decided, why, and when. Change these only with a reason, and note the change here
(mark reversed decisions as reversed rather than deleting them).

## Scope
- 2026-10-16: Robustness pass. Fix the review findings (disconnects, logout mid-game,
  server-side validation, numeric leaderboard sort, debug/secret handling, docs) without
  changing the game design.

## Platform and hosting
- 2026-10-16: Still runs on Flask-SocketIO's built-in Werkzeug server (threading mode) for
  local/LAN play. Debug mode is opt-in through `DEBUG=1`; default off, because debug mode on
  0.0.0.0 exposes the Werkzeug debugger (remote code execution).

## Data and secrets
- 2026-10-16: State stays in memory (lost on restart), as before. `SECRET_KEY` comes from the
  environment or `.env`; without it the app generates a random key per start (sessions then
  end on restart). `.env.example` documents the variables; `.env` is git-ignored.

## Behaviour and rules
- 2026-10-16: Kept as-is: payoffs 3/3, 0/5, 5/0, 1/1; 5–9 random rounds; challenges are
  auto-accepted; leaderboard is average score per round, shown only for players with 7+ games;
  a game ended early (leave, logout, disconnect) still counts as a game played and keeps the
  rounds already scored.
- 2026-10-16: A closed tab or lost connection ends that player's match (the opponent returns to
  the lobby) and frees the username, after a grace period (`DISCONNECT_GRACE_SECONDS`,
  default 10) so that a page reload, including the automatic one right after login, doesn't
  end the game. The name stays reserved during the grace period. Returning with the same
  username restores the player's stats, as logging back in already did.
- 2026-10-16: When a player goes offline (logout or lost connection) and has never played a
  game or round, they are forgotten; others are kept for the leaderboard (before: logout kept
  only players whose total score was above 0, so a player who scored 0 points lost their
  games played).
- 2026-10-16: Usernames are trimmed and must be 1–30 characters.
- 2026-10-16: Each login stores a random token in the session cookie and on the player; page
  loads and logout only act for a cookie whose token matches, so an old cookie can't take a
  name back from someone who logged in with it later (found in the pre-release review).
- 2026-10-16: The lobby lists only online players (before: logged-out players with a score
  stayed listed and challenging them crashed the server).

## UI
- 2026-10-16: The client shows an alert when a challenge is refused (the server already sent
  `challenge_failed`; the client had no handler).

## Repository
- 2026-10-16: Conda env `prisoners_dilemma` from `environment.yml`; runtime pins in
  `requirements.txt`, test/lint tools in `requirements-dev.txt`; pytest and ruff configured in
  `pyproject.toml`.

## Licence
- MIT, copyright Brian Yu (2026-10-18), matching the name already on the commits. LICENSE file at the repo root.
