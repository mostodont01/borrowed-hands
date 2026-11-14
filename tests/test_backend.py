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
