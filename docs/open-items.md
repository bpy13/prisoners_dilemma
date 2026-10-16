# Open items

As of 2026-10-16. Tick off, or move to `decisions.md` when settled. A bug that will be fixed goes
here; a limit or trap we live with goes in `known-issues.md`. Each item in one place only.

## Blockers

## Waiting on the user

1. **No LICENSE file.** The README says "MIT License" but the repo has no `LICENSE` file, so
   legally nothing is granted. Default: add a standard MIT `LICENSE` with your name and 2025.
2. **Old screenshots stay in git history.** The four `png/` screenshots were shrunk (about
   6.0 MB to 3.7 MB), but the original files remain in past commits, so cloning is not
   smaller. Removing them means rewriting pushed history (force push). Default: leave history
   alone.

## Pending work

## Later

- **Two tabs, one login.** If the same browser opens the game in a second tab, the newest tab
  takes over and the older one is sent back to the login screen (before, both tabs could act
  as the player). Fine for now; revisit if players complain.
- **Dev server log noise.** When a websocket closes, Werkzeug's dev server logs a harmless
  `code 400, message Bad request ...` line. The game is unaffected. A production server
  (e.g. eventlet or gunicorn) would remove it, if the game is ever hosted publicly.
- **In-memory state.** All scores are lost on restart (as before). A small SQLite file would
  keep the leaderboard, if wanted.
