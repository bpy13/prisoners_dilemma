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
  the lobby) and frees the username. Returning with the same username restores the player's
  stats, as logging back in already did.
- 2026-10-16: On logout, a player who has never played a round is forgotten; others are kept
  for the leaderboard (before: kept only if their total score was above 0, so a player who
  scored 0 points lost their games played).
- 2026-10-16: The lobby lists only online players (before: logged-out players with a score
  stayed listed and challenging them crashed the server).

## UI
- 2026-10-16: The client shows an alert when a challenge is refused (the server already sent
  `challenge_failed`; the client had no handler).

## Repository
- 2026-10-16: Conda env `prisoners_dilemma` from `environment.yml`; runtime pins in
  `requirements.txt`, test/lint tools in `requirements-dev.txt`; pytest and ruff configured in
  `pyproject.toml`.
