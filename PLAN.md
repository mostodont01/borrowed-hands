# Borrowed Hands — plan

Claude borrows your hands to use websites that block bots (Alza, or any other).
Claude can read the page, but you are the one who clicks and types, in a real browser,
so the site sees a real person.

## The flow

1. You ask Claude to find something (e.g. "find a USB Wi-Fi dongle on Alza").
2. Claude calls the MCP tool `open_browser(url)`. A window opens: a web view on the left and
   Claude's panel on the right.
3. Claude writes instructions in the panel ("Search for 'USB WiFi dongle'"). You do them.
4. Claude reads the pages by itself (and may open pages on the same site at a human pace),
   picks the best results and closes the window **immediately** when it is done. It tells you
   the results in the chat.

## Architecture

```
Claude Code ──MCP (stdio)──> hands mcp  ──local socket (JSON lines)──>  hands window (PySide6 + QML)
                                 ▲                                          ├─ WebEngineView (persistent profile)
              hands CLI ─────────┘ (same client, for testing/scripting)     └─ panel: instruction, history, reply, Done
```

- **Window app** (`borrowed_hands.app`): PySide6 + QML, Qt WebEngine. One process per session.
  Listens on a local socket and accepts JSON-line commands.
- **Client** (`borrowed_hands.client`): starts the window if needed and sends commands. Used by
  both the MCP server and the CLI.
- **MCP server** (`hands mcp`): thin layer over the client.
- **CLI** (`hands`): `hands open <url>`, `hands say "<text>"`, `hands read`, `hands wait`,
  `hands close`.
- Logic that doesn't need Qt (timeout state machine, page-summary formatting, protocol) is kept
  separate and tested on its own.

## MCP tools

| Tool | What it does |
|---|---|
| `open_browser(url)` | Opens the window on `url` |
| `instruct(text)` | Shows an instruction in the panel, then waits like `wait` |
| `wait()` | Waits up to ~50 s for progress (page load, Done, reply). Returns the event, `still_waiting`, or `session_ended` |
| `read_page()` | Page text with interactive elements numbered (`[12] button "Hledat"`), URL, title |
| `navigate(url)` | Claude opens a page itself (human pace, same site) |
| `close_browser()` | Closes the window immediately |

## Timeouts

Two separate things:

1. **MCP call limit** (Claude Code side): no call blocks for long. `wait` returns
   `still_waiting` after ~50 s and Claude simply calls it again. The user never sees this.
2. **Inactivity rule** (app side): the timer resets on any progress (page load, typing,
   clicking, Done, reply). After **2 min** without progress, a popup over the window asks
   *"Timeout. Continue the search? Yes / No"*. **Yes** resets the timer. **No**, closing the
   window, or **no answer within 1 min** closes the window. Claude's next `wait` then returns
   `session_ended`.

## Browser details

- Persistent profile in `~/.local/share/borrowed-hands/profile` (cookies, logins, passed
  captchas survive).
- User agent of normal desktop Chrome (the default "QtWebEngine" string gets blocked by some sites).
- Password field contents are never sent to Claude.
- If a captcha / block page appears, the panel asks the user to solve it.
- Normal window with focus. On Wayland an app can't force "always on top".

## Milestones

1. **Window app**: web view, panel, timeout popup, profile, local socket, CLI. Headless tests
   against local test pages.
2. **MCP server**: the tools above; check Claude Code's real tool timeout and tune `wait`.
3. **First real Alza session**: search, compare, close. Fix what gets in the way.
4. **Polish**: a Claude Code skill for guiding a human (one short step at a time), optional
   product-list extractors, app menu entry.
