# Architecture

One Python process (`python app.py`) serves the page, a few HTTP routes and a Socket.IO
connection per browser tab. All state is in memory in a single `GameState` object; nothing is
written to disk.

## Flow

```
browser loads /  (templates/index.html + static/socketIO.js)
  └─ socket connects, sends 'initialize'
       ├─ no valid login cookie  → 'login_page' (carries the socket id)
       │    └─ POST /login {username, sid} → cookie set, page reloads, 'initialize' again
       ├─ free                   → 'lobby_page'; 'issue_challenge' starts a match (auto-accepted)
       └─ in a match             → 'game_page'; 'submit_option' each round → 'game_result'
            └─ last round / 'terminate_game' / logout / lost connection
                 → 'game_end' + 'lobby_page' for whoever is still online
```

## Modules

| Module | Role |
|---|---|
| `game.py` | `Player`, `Match`, `GameState`, payoffs and rules; no Flask |
| `app.py` | Flask routes (`/`, `/login`, `/logout`, `/leaderboard`), socket events, config from env |
| `static/socketIO.js` | Browser side of the protocol; page switching and alerts |
| `templates/` | `index.html` (all three screens), `leaderboard.html` |

## Data

- `GameState.players`: name → `Player` (socket id, total score, rounds and games played, current
  match, login token, reconnect token). Kept for players with history, so stats survive logout.
- `Match`: both players, rounds left, this round's decisions, per-round scores.
- Locking: socket handlers and routes hold `state.lock` (an RLock) while touching state.
- Disconnects: the match and name are held for `DISCONNECT_GRACE_SECONDS` by a background task
  before `take_offline` ends the match.

## External services and costs

None. Bootstrap and the Socket.IO client load from cdnjs in the browser.
