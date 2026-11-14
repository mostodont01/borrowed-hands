"""MCP tools with a fake client (no window)."""

import anyio
import pytest

from borrowed_hands import client, mcp_server


class FakeClient:
    def __init__(self):
        self.calls = []
        self.waits = []  # queued wait results
        self.running = True

    def _check(self):
        if not self.running:
            raise client.NotRunning("closed")

    def open_window(self, url):
        self.calls.append(("open", url))
        return {"ok": True, "started": True}

    def say(self, text, element=None):
        self._check()
        self.calls.append(("say", text, element))
        return {"ok": True, "highlighted": element != 99} if element else {"ok": True}

    def wait(self, timeout=50):
        self.calls.append(("wait", timeout))
        if self.waits:
            return self.waits.pop(0)
        return {"ok": True, "status": "still_waiting", "events": []}

    def read(self, full=False):
        self._check()
        return {"ok": True, "page": {"url": "u", "title": "t", "elements": 0, "text": "x"}}

    def navigate(self, url):
        self._check()
        self.calls.append(("navigate", url))
        return {"ok": True}

    def close(self):
        return {"ok": True}


@pytest.fixture
def fake(monkeypatch):
    f = FakeClient()
    for name in ("open_window", "say", "wait", "read", "navigate", "close"):
        monkeypatch.setattr(client, name, getattr(f, name))
    monkeypatch.setattr(mcp_server, "MIN_NAVIGATE_GAP", 0.0)
    return f


def loaded(title="t"):
    return {"ok": True, "status": "events", "events": [{"type": "page_loaded", "url": "u", "title": title}]}


def run(coro):
    return anyio.run(lambda: coro)


def test_tools_registered():
    names = {t.name for t in anyio.run(mcp_server.server.list_tools)}
    assert names == {"open_browser", "instruct", "wait", "read_page", "navigate", "close_browser"}


def test_open_browser_waits_for_load(fake):
    fake.waits = [{"ok": True, "status": "still_waiting", "events": []}, loaded("Alza")]
    result = anyio.run(mcp_server.open_browser, "alza.cz")
    assert result["events"][0]["title"] == "Alza"
    assert fake.calls[0] == ("open", "alza.cz")


def test_instruct_says_then_waits(fake):
    fake.waits = [{"ok": True, "status": "events", "events": [{"type": "done"}]}]
    result = anyio.run(mcp_server.instruct, "Search for X", None)
    assert fake.calls[0] == ("say", "Search for X", None)
    assert fake.calls[1][0] == "wait" and fake.calls[1][1] <= 50
    assert result["events"] == [{"type": "done"}]


def test_instruct_reports_missing_element(fake):
    result = anyio.run(mcp_server.instruct, "Click it", 99)
    assert "not found" in result["note"]


def test_wait_still_waiting(fake):
    assert anyio.run(mcp_server.wait)["status"] == "still_waiting"


def test_navigate_waits_for_load(fake):
    fake.waits = [loaded("Detail")]
    result = anyio.run(mcp_server.navigate, "https://alza.cz/x")
    assert ("navigate", "https://alza.cz/x") in fake.calls
    assert result["events"][0]["title"] == "Detail"


def test_tools_when_window_closed(fake):
    fake.running = False
    result = anyio.run(mcp_server.read_page)
    assert result["ok"] is False and "open_browser" in result["error"]
