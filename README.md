# Borrowed Hands

Claude borrows your hands to use websites that block bots.

Claude opens a browser window with a panel on the right, tells you what to do ("search for
'USB WiFi dongle'"), reads the pages itself and closes the window when it has what it needs.
You click and type in a real browser, so sites like Alza see a real person.

Status: usable. Tested in real sessions on Alza (search, reading results, product pages). See [PLAN.md](PLAN.md).

## Try it

```sh
uv sync
uv run hands open alza.cz          # opens the window
uv run hands say "Search for 'USB WiFi dongle'"
uv run hands wait                  # waits for a page load, Done, a reply, or the timeout
uv run hands read                  # the page as text, interactive elements numbered (--full: no hiding)
uv run hands say "Open this one" -e 12   # highlight element 12
uv run hands import alza.cz    # share your Firefox login for this site
uv run hands close
```

After 2 minutes without progress the window asks whether to continue; with no answer it
closes a minute later.

## Use it from Claude Code

```sh
claude mcp add -s user borrowed-hands -- "$PWD/.venv/bin/hands" mcp
```

Then ask Claude e.g. "find a USB Wi-Fi dongle on Alza". Tools: `open_browser`, `instruct`, `wait`, `read_page`, `navigate`, `import_login`, `close_browser`.

## Development

```sh
uv sync
QT_QPA_PLATFORM=offscreen uv run pytest
```
