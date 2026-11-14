"""MCP server: lets Claude open the window, guide the user and read pages. Run with `hands mcp`."""

import time

import anyio
from mcp.server.mcpserver import MCPServer

from borrowed_hands import client

INSTRUCTIONS = """\
Borrowed Hands: use websites that block bots (e.g. alza.cz) through the user's hands.
A window opens with a real browser and a panel where your instructions appear. The user
clicks and types; you read the pages.

Workflow: open_browser(url) -> read_page -> instruct("...") / navigate(url) -> read_page ...
-> close_browser() as soon as you have what you need (the window closes immediately; tell the
user the results in the chat).

Rules:
- Read pages yourself whenever you can; only ask the user for what you can't do yourself
  (typing into search boxes, clicking buttons, solving captchas, logging in).
- One short, concrete step per instruction ("Type 'USB WiFi dongle' into the search box and
  press Enter"). Pass element=N (from read_page) to highlight what to click.
- page_loaded also fires when a site changes the page without reloading ("without_reload").
- instruct and wait return events: page_loaded, done, cant, reply (user's text),
  timeout_prompt, session_ended. "still_waiting" means nothing happened yet: just call wait
  again. Never give up on still_waiting; the user may be slow.
- timeout_prompt: the user was idle for 2 min and is asked whether to continue. Keep calling
  wait. session_ended: the window is gone (user stopped, closed it, or timed out). Stop and
  report what you found so far.
- navigate is for loading pages yourself (e.g. product details). Keep it human-paced and on the
  same site; if a captcha or block page appears, ask the user to solve it.
- Never ask for passwords or payment details, and never complete a purchase.
"""

WAIT_SECONDS = 50.0  # stays well under Claude Code's MCP tool timeout
MIN_NAVIGATE_GAP = 3.0  # seconds between pages Claude loads itself

server = MCPServer("borrowed-hands", instructions=INSTRUCTIONS)
_last_navigate = 0.0


async def _call(fn, *args, **kwargs):
    """Run a blocking client call without blocking the MCP event loop."""
    try:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))
    except client.NotRunning:
        return {"ok": False, "error": "The browser window is not open. Call open_browser first."}


async def _wait_for_load(timeout: float) -> dict:
    """Wait until a page_loaded (or session_ended) event, collecting everything seen."""
    deadline = time.monotonic() + timeout
    events: list[dict] = []
    while (left := deadline - time.monotonic()) > 0:
        result = await _call(client.wait, min(left, WAIT_SECONDS))
        events += result.get("events", [])
        if any(e["type"] in ("page_loaded", "session_ended") for e in events):
            break
    return {"ok": True, "status": "events" if events else "still_waiting", "events": events}


@server.tool()
async def open_browser(url: str) -> dict:
    """Open the browser window on url (or load url if it is already open) and wait for the page."""
    started = await _call(client.open_window, url)
    if not started.get("ok"):
        return started
    loaded = await _wait_for_load(30)
    return {"ok": True, "events": loaded["events"]}


@server.tool()
async def instruct(text: str, element: int | None = None, copy: str | None = None) -> dict:
    """Show an instruction in the panel (optionally highlight element N from read_page),
    then wait up to ~50 s for the user. Returns events, or status "still_waiting".
    The panel's Copy button copies `copy`, or else the first quoted part of `text`
    (so put the text to type in quotes)."""
    said = await _call(client.say, text, element, copy)
    if not said.get("ok"):
        return said
    result = await _call(client.wait, WAIT_SECONDS)
    if element and not said.get("highlighted", True):
        result["note"] = f"element {element} not found on the current page; read_page again"
    return result


@server.tool()
async def wait() -> dict:
    """Wait up to ~50 s for progress: page_loaded, done, cant, reply, timeout_prompt or
    session_ended. "still_waiting" means nothing happened yet; call wait again."""
    return await _call(client.wait, WAIT_SECONDS)


@server.tool()
async def read_page(full: bool = False) -> dict:
    """The current page as text: headings, text and numbered interactive elements
    ([12] button "Hledat", links with their URL). Compact by default: repeated buttons and
    lines are hidden after the first (a footer lists them) and same-site links are relative.
    full=True shows everything. Password values are never included."""
    return await _call(client.read, full)


@server.tool()
async def navigate(url: str) -> dict:
    """Load url yourself (same site, human pace) and wait for it to load."""
    global _last_navigate
    gap = MIN_NAVIGATE_GAP - (time.monotonic() - _last_navigate)
    if gap > 0:
        await anyio.sleep(gap)
    _last_navigate = time.monotonic()
    result = await _call(client.navigate, url)
    if not result.get("ok"):
        return result
    loaded = await _wait_for_load(30)
    return {"ok": True, "events": loaded["events"]}


@server.tool()
async def close_browser() -> dict:
    """Close the window immediately. Call this as soon as you have what you need."""
    return await _call(client.close)


def main() -> None:
    server.run("stdio")
