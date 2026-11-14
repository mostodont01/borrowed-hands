"""End to end: start the real window (headless) and drive it through the client."""

import os
import subprocess
import sys
import time

import pytest

from borrowed_hands import client

PAGES = os.path.join(os.path.dirname(__file__), "pages")


@pytest.fixture
def window_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDS_SOCKET", str(tmp_path / "hands.sock"))
    monkeypatch.setenv("HANDS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", (flags + " --no-sandbox").strip())
    yield tmp_path
    client.close()


def wait_for(event_type, timeout=20):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        result = client.wait(timeout=2)
        seen += result["events"]
        for e in result["events"]:
            if e["type"] == event_type:
                return e
    raise AssertionError(f"no {event_type} event, saw {seen}")


def test_open_read_say_navigate_close(window_env):
    url = "file://" + os.path.join(PAGES, "shop.html")
    assert client.open_window(url)["ok"]
    wait_for("page_loaded")

    page = client.read()["page"]
    assert page["title"] == "Test Shop"
    text = page["text"]
    assert "# Test Shop" in text
    assert 'input:search "Hledat" value="wifi"' in text
    assert "secret123" not in text and "password, value hidden" in text
    assert "hiddenvalue" not in text
    assert "Invisible text" not in text
    assert 'button "Hledat"' in text
    assert "Welcome to the test shop." in text

    button_id = next(int(l[1:l.index("]")]) for l in text.splitlines() if 'button "Hledat"' in l)
    assert client.say("Click Hledat", element=button_id) == {"ok": True, "highlighted": True}

    assert client.wait(timeout=0.3)["status"] == "still_waiting"

    client.navigate("file://" + os.path.join(PAGES, "results.html"))
    loaded = wait_for("page_loaded")
    assert loaded["title"] == "Results"
    assert "Dongle B — 349 Kč" in client.read()["page"]["text"]

    assert client.close()["ok"]
    deadline = time.monotonic() + 10
    while client.is_running() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not client.is_running()
    assert client.wait(timeout=1)["events"][0]["type"] == "session_ended"


def test_inactivity_timeout_closes_window(window_env, monkeypatch):
    monkeypatch.setenv("HANDS_IDLE_LIMIT", "1")
    monkeypatch.setenv("HANDS_PROMPT_LIMIT", "1")
    client.open_window("about:blank")
    wait_for("timeout_prompt", timeout=15)
    ended = wait_for("session_ended", timeout=15)
    assert ended["reason"] == "timeout"


def test_url_change_without_reload(window_env):
    client.open_window("file://" + os.path.join(PAGES, "spa.html"))
    wait_for("page_loaded")
    event = wait_for("page_loaded")
    assert event.get("without_reload") and event["url"].endswith("?q=dongle")
    assert "2 results" in client.read()["page"]["text"]


def test_cookies_survive_restart(window_env):
    """Open a local http page that sets a cookie, close the window, reopen: the cookie is back."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen = self.headers.get("Cookie") or "none"
            body = f"<html><head><title>c</title></head><body>cookie={seen}</body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "consent=yes; Max-Age=86400; Path=/")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_port}/"
    try:
        client.open_window(url)
        wait_for("page_loaded")
        assert "cookie=none" in client.read()["page"]["text"]
        client.close()
        deadline = time.monotonic() + 10
        while client.is_running() and time.monotonic() < deadline:
            time.sleep(0.1)
        time.sleep(1)  # let the old process flush the cookie store and exit

        client.open_window(url)
        wait_for("page_loaded")
        assert "cookie=consent=yes" in client.read()["page"]["text"]
    finally:
        httpd.shutdown()
