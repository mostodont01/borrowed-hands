"""Backend command handling without a real web view (QML side is faked)."""

import pytest

from borrowed_hands.app import Backend, normalize_url


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(qapp):
    clock = Clock()
    backend = Backend(clock=clock, idle_limit=120, prompt_limit=60)
    backend._tick.stop()  # drive ticks by hand
    replies = []
    return backend, clock, replies


def test_normalize_url():
    assert normalize_url("alza.cz") == "https://alza.cz"
    assert normalize_url("http://x.cz") == "http://x.cz"
    assert normalize_url("about:blank") == "about:blank"
    assert normalize_url("") == "about:blank"


def test_wait_returns_queued_events(setup):
    backend, _, replies = setup
    backend.done()
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    assert replies == [{"ok": True, "status": "events", "events": [{"type": "done"}]}]


def test_wait_is_answered_by_later_event(setup):
    backend, _, replies = setup
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    assert replies == []
    backend.reply("  the blue one ")
    assert replies[0]["events"] == [{"type": "reply", "text": "the blue one"}]


def test_wait_times_out_with_still_waiting(setup, qtbot):
    backend, _, replies = setup
    backend.handle({"cmd": "wait", "timeout": 0.1}, replies.append)
    qtbot.waitUntil(lambda: bool(replies), timeout=2000)
    assert replies[0] == {"ok": True, "status": "still_waiting", "events": []}


def test_say_sets_instruction_and_history(setup):
    backend, _, replies = setup
    scripts = []
    backend.runJs.connect(lambda rid, js: scripts.append(js))
    backend.handle({"cmd": "say", "text": "Search for 'USB WiFi dongle'"}, replies.append)
    assert replies == [{"ok": True}]
    assert backend.instruction == "Search for 'USB WiFi dongle'"
    assert backend.history[-1] == {"who": "claude", "text": "Search for 'USB WiFi dongle'"}
    assert scripts  # clears old highlight


def test_read_uses_js_result(setup):
    backend, _, replies = setup
    backend.runJs.connect(
        lambda rid, js: backend.jsResult(rid, '{"url": "u", "title": "t", "elements": 0, "items": [{"t": "text", "s": "hi"}]}')
    )
    backend.handle({"cmd": "read"}, replies.append)
    assert replies[0] == {"ok": True, "page": {"url": "u", "title": "t", "elements": 0, "text": "hi"}}


def test_timeout_prompt_then_no_answer_ends(setup):
    backend, clock, replies = setup
    closed = []
    backend.closeRequested.connect(lambda: closed.append(True))
    clock.now = 120
    backend.tick()
    assert backend.promptVisible
    clock.now = 180
    backend.tick()
    assert closed and backend.ended_reason == "timeout"
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    types = [e["type"] for e in replies[0]["events"]]
    assert types == ["timeout_prompt", "session_ended"]


def test_prompt_yes_keeps_session(setup):
    backend, clock, _ = setup
    clock.now = 120
    backend.tick()
    backend.answerPrompt(True)
    assert not backend.promptVisible
    assert backend.ended_reason is None


def test_prompt_no_closes(setup):
    backend, clock, _ = setup
    closed = []
    backend.closeRequested.connect(lambda: closed.append(True))
    clock.now = 120
    backend.tick()
    backend.answerPrompt(False)
    assert closed and backend.ended_reason == "user_stopped"


def test_close_command(setup):
    backend, _, replies = setup
    closed = []
    backend.closeRequested.connect(lambda: closed.append(True))
    backend.handle({"cmd": "close"}, replies.append)
    assert replies == [{"ok": True}] and closed


def test_unknown_command(setup):
    backend, _, replies = setup
    backend.handle({"cmd": "dance"}, replies.append)
    assert replies[0]["ok"] is False


def test_url_change_without_reload_is_reported(setup, qtbot):
    backend, _, replies = setup
    backend.pageLoaded("https://x.cz/", "X")
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    replies.clear()
    backend.pageChanged("https://x.cz/?q=a", "X")
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    qtbot.waitUntil(lambda: bool(replies), timeout=3000)
    event = replies[0]["events"][0]
    assert event == {"type": "page_loaded", "url": "https://x.cz/?q=a", "title": "X", "without_reload": True}


def test_url_change_during_load_not_double_reported(setup, qtbot):
    backend, _, replies = setup
    backend.pageLoading()
    backend.pageChanged("https://x.cz/next", "")
    qtbot.wait(1000)
    backend.pageLoaded("https://x.cz/next", "Next")
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    assert [e["type"] for e in replies[0]["events"]] == ["page_loaded"]
    assert "without_reload" not in replies[0]["events"][0]


def test_say_sets_copy_text_and_waiting_status(setup):
    backend, _, replies = setup
    backend.handle({"cmd": "say", "text": 'Type "esperanza vr box" and press Enter'}, replies.append)
    assert backend.copyText == "esperanza vr box"
    assert (backend.status, backend.statusKind) == ("Waiting for you…", "waiting")
    backend.handle({"cmd": "say", "text": 'Type "a"', "copy": "explicit"}, replies.append)
    assert backend.copyText == "explicit"


def test_status_shows_detection_instantly(setup):
    backend, _, replies = setup
    backend.handle({"cmd": "say", "text": "Search"}, replies.append)
    backend.pageLoading()
    assert backend.status == "Page loading…"
    backend.pageLoaded("https://x.cz/?q=a", "X")
    assert backend.statusKind == "detected" and "detected" in backend.status
    backend.handle({"cmd": "read"}, lambda r: None)
    assert backend.status == "Claude is reading the page…"
    backend.done()
    assert backend.status == "✓ Done sent to Claude"


def test_shorten_url_trims_long_query():
    from borrowed_hands.app import shorten_url

    short = "https://www.alza.cz/search.htm?exps=filament"
    assert shorten_url(short) == short
    long_q = "https://accounts.google.com/v3/signin?" + "state=" + "x" * 500 + "&email=me@x.cz"
    out = shorten_url(long_q)
    assert len(out) < 150 and out.startswith("https://accounts.google.com/v3/signin?")
    assert "me@x.cz" not in out
    assert shorten_url("about:blank") == "about:blank"


def test_page_loaded_event_url_is_shortened(setup):
    backend, _, replies = setup
    backend.pageLoaded("https://x.cz/a?" + "q=" + "z" * 300, "T")
    backend.handle({"cmd": "wait", "timeout": 5}, replies.append)
    url = replies[0]["events"][0]["url"]
    assert len(url) < 120 and url.endswith("…")
    # internal state keeps the full URL
    assert backend.url.endswith("z" * 300)


class FakeStore:
    def __init__(self):
        self.cookies = []

    def setCookie(self, cookie, origin):
        self.cookies.append((bytes(cookie.name()).decode(), bytes(cookie.value()).decode(),
                             origin.toString()))


class FakeProfile:
    def __init__(self):
        self._store = FakeStore()

    def cookieStore(self):
        return self._store


def test_import_login_injects_cookies(setup, monkeypatch):
    backend, _, replies = setup
    profile = FakeProfile()
    backend.set_profile(profile)
    backend.url = "https://www.alza.cz/"
    navigated = []
    backend.navigateRequested.connect(navigated.append)

    from borrowed_hands import firefox_import

    monkeypatch.setattr(
        firefox_import, "read_cookies",
        lambda domain, db_path=None: [
            {"name": "sid", "value": "abc", "host": ".alza.cz", "path": "/", "expiry": 2000000000,
             "secure": True, "http_only": True, "same_site": "lax"},
        ],
    )
    backend.handle({"cmd": "import_login", "domain": "alza.cz"}, replies.append)
    assert replies[0] == {"ok": True, "imported": 1, "domain": "alza.cz"}
    assert profile._store.cookies[0][:2] == ("sid", "abc")
    assert navigated == ["https://www.alza.cz/"]  # page reloaded to pick up the login
    assert backend.statusKind == "detected"


def test_import_login_reports_when_not_logged_in(setup, monkeypatch):
    backend, _, replies = setup
    backend.set_profile(FakeProfile())
    from borrowed_hands import firefox_import

    monkeypatch.setattr(firefox_import, "read_cookies", lambda domain, db_path=None: [])
    backend.handle({"cmd": "import_login", "domain": "alza.cz"}, replies.append)
    assert replies[0]["ok"] and replies[0]["imported"] == 0 and "note" in replies[0]


def test_import_login_firefox_error(setup, monkeypatch):
    backend, _, replies = setup
    backend.set_profile(FakeProfile())
    from borrowed_hands import firefox_import

    def boom(domain, db_path=None):
        raise firefox_import.FirefoxError("no Firefox cookie database found")

    monkeypatch.setattr(firefox_import, "read_cookies", boom)
    backend.handle({"cmd": "import_login", "domain": "alza.cz"}, replies.append)
    assert replies[0]["ok"] is False and "Firefox" in replies[0]["error"]


def test_set_cookie_builds_real_cookie():
    from borrowed_hands.app import Backend

    store = FakeStore()
    ok = Backend._set_cookie(store, {
        "name": "sid", "value": "v", "host": ".alza.cz", "path": "/", "expiry": 2000000000,
        "secure": True, "http_only": True, "same_site": "strict",
    })
    assert ok and store.cookies[0] == ("sid", "v", "https://alza.cz/")
