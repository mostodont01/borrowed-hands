# Borrowed Hands

Claude borrows your hands to use websites that block bots.

Claude opens a browser window with a panel on the right, tells you what to do ("search for
'USB WiFi dongle'"), reads the pages itself and closes the window when it has what it needs.
You click and type in a real browser, so sites like Alza see a real person.

Status: early development. See [PLAN.md](PLAN.md).

## Development

```sh
uv sync
QT_QPA_PLATFORM=offscreen uv run pytest
```
