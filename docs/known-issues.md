# Known issues and limits

How things behave that a newcomer would trip over: limits we live with, traps, gotchas.
Bugs that will be fixed go in `open-items.md` instead.

## Players and sessions

- **Two tabs, one login.** If the same browser opens the game in a second tab, the newest tab
  takes over and the older one is sent back to the login screen.
- **Old login cookies stop working once someone else takes the name.** Each login stores a
  random token in the cookie; if another person logs in with that name after you went
  offline, your old tab shows the login screen instead of taking the name back.
- **In-memory state.** All players and scores are lost when the server restarts. A small
  SQLite file would keep the leaderboard, if wanted.

## Server

- **Dev server only.** `python app.py` uses Werkzeug's development server, fine for a home or
  office network, not for the internet.
- **Log noise on websocket close.** When a browser's websocket closes, Werkzeug logs a
  harmless `code 400, message Bad request ...` line. The game is unaffected.
