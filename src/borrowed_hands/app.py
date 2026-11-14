"""The window: web view + Claude's panel. Run with `python -m borrowed_hands.app [url]`.

It listens on a local socket (see paths.socket_path) and accepts one JSON request per
connection (see protocol.py). Commands:

    ping                       -> {ok, url, title}
    say {text, element?}       -> show an instruction (optionally highlight element N)
    read                       -> {ok, page: {url, title, elements, text}}
    wait {timeout}             -> {ok, status: "events" | "still_waiting", events: [...]}
    navigate {url}             -> start loading url
    close                      -> close the window immediately
"""

import itertools
import re
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEvent,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QQuickWebEngineProfile, QtWebEngineQuick

from borrowed_hands import pagetext, paths, protocol
from borrowed_hands.instruction import STATUS_FOR_EVENT, copy_text_for
from borrowed_hands.timeout import InactivityTimer, Phase

HERE = Path(__file__).parent
READ_JS = (HERE / "js" / "read_page.js").read_text()
HIGHLIGHT_JS = (HERE / "js" / "highlight.js").read_text()

INPUT_EVENTS = {
    QEvent.Type.KeyPress,
    QEvent.Type.MouseButtonPress,
    QEvent.Type.Wheel,
    QEvent.Type.TouchBegin,
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" not in url and not url.startswith(("about:", "file:", "data:")):
        url = "https://" + url
    return url


class Backend(QObject):
    """State shown in the window plus the command handling. QML talks to this object."""

    instructionChanged = Signal()
    statusChanged = Signal()
    historyChanged = Signal()
    promptChanged = Signal()
    secondsLeftChanged = Signal()
    navigateRequested = Signal(str)
    runJs = Signal(int, str)
    closeRequested = Signal()

    def __init__(self, clock=time.monotonic, idle_limit=120.0, prompt_limit=60.0):
        super().__init__()
        self._clock = clock
        self._timer = InactivityTimer(clock(), idle_limit, prompt_limit)
        self._instruction = ""
        self._copy_text = ""
        self._status = ""
        self._status_kind = "idle"  # idle | waiting | working | detected
        self._history: list[dict] = []
        self._events: list[dict] = []
        self._waiter = None  # (reply callback, QTimer)
        self._js_ids = itertools.count(1)
        self._js_callbacks: dict[int, callable] = {}
        self._seconds_left = 0
        self.ended_reason: str | None = None
        self.url = ""
        self.title = ""
        self._loading = False
        self._reported_url = ""
        self._url_settle = QTimer(self)
        self._url_settle.setSingleShot(True)
        self._url_settle.setInterval(400)
        self._url_settle.timeout.connect(self._url_settled)

        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self.tick)
        self._tick.start()

    # ---- properties for QML ------------------------------------------------------------

    @Property(str, notify=instructionChanged)
    def copyText(self):
        return self._copy_text

    @Property(str, notify=statusChanged)
    def status(self):
        return self._status

    @Property(str, notify=statusChanged)
    def statusKind(self):
        return self._status_kind

    def set_status(self, text: str, kind: str):
        self._status, self._status_kind = text, kind
        self.statusChanged.emit()

    @Property(str, notify=instructionChanged)
    def instruction(self):
        return self._instruction

    @Property("QVariantList", notify=historyChanged)
    def history(self):
        return self._history

    @Property(bool, notify=promptChanged)
    def promptVisible(self):
        return self._timer.phase is Phase.PROMPT

    @Property(int, notify=secondsLeftChanged)
    def secondsLeft(self):
        return self._seconds_left

    # ---- called from QML ---------------------------------------------------------------

    @Slot()
    def activity(self):
        self._timer.activity(self._clock())

    @Slot()
    def done(self):
        self._add_history("you", "Done")
        self.push_event({"type": "done"})

    @Slot()
    def cant(self):
        self._add_history("you", "Can't do that")
        self.push_event({"type": "cant"})

    @Slot(str)
    def reply(self, text):
        text = text.strip()
        if text:
            self._add_history("you", text)
            self.push_event({"type": "reply", "text": text})

    @Slot(bool)
    def answerPrompt(self, keep_going):
        self._timer.answer(keep_going, self._clock())
        self.promptChanged.emit()
        if self._timer.phase is Phase.ENDED:
            self.end_session("user_stopped")

    @Slot()
    def windowClosing(self):
        self.end_session("window_closed", close=False)

    @Slot(str, str)
    def pageLoaded(self, url, title):
        self.url, self.title = url, title
        self._loading = False
        self._reported_url = url
        self.activity()
        self.push_event({"type": "page_loaded", "url": url, "title": title})

    @Slot()
    def pageLoading(self):
        self._loading = True
        self.set_status("Page loading…", "working")

    @Slot()
    def pageLoadFailed(self):
        self._loading = False

    @Slot(str, str)
    def pageChanged(self, url, title):
        """URL or title changed. If the URL changed without a page load (a single-page app
        switched content, e.g. Alza's search), report it once things settle."""
        self.url, self.title = url, title
        if url != self._reported_url:
            self._url_settle.start()

    def _url_settled(self):
        if self._loading or self.url == self._reported_url:
            return
        self._reported_url = self.url
        self.activity()
        self.push_event({"type": "page_loaded", "url": self.url, "title": self.title, "without_reload": True})

    @Slot(int, str)
    def jsResult(self, request_id, result_json):
        callback = self._js_callbacks.pop(request_id, None)
        if callback:
            callback(json.loads(result_json) if result_json else None)

    # ---- session logic -----------------------------------------------------------------

    def tick(self):
        now = self._clock()
        before = self._timer.phase
        phase = self._timer.tick(now)
        left = self._timer.seconds_left(now)
        if left != self._seconds_left:
            self._seconds_left = left
            self.secondsLeftChanged.emit()
        if phase is not before:
            self.promptChanged.emit()
            if phase is Phase.PROMPT:
                self.push_event({"type": "timeout_prompt"}, count_as_activity=False)
            elif phase is Phase.ENDED:
                self.end_session("timeout")

    def push_event(self, event: dict, count_as_activity: bool = True):
        if count_as_activity:
            self.activity()
        if event["type"] in STATUS_FOR_EVENT:
            self.set_status(STATUS_FOR_EVENT[event["type"]], "detected")
        self._events.append(event)
        self._flush_waiter()

    def end_session(self, reason: str, close: bool = True):
        if self.ended_reason:
            return
        self.ended_reason = reason
        self._timer.end()
        self._events.append({"type": "session_ended", "reason": reason})
        self._flush_waiter()
        if close:
            self.closeRequested.emit()

    def _flush_waiter(self, timed_out: bool = False):
        if not self._waiter:
            return
        if not self._events and not timed_out:
            return
        reply, timer = self._waiter
        self._waiter = None
        timer.stop()
        events, self._events = self._events, []
        status = "events" if events else "still_waiting"
        reply({"ok": True, "status": status, "events": events})

    def _add_history(self, who: str, text: str):
        self._history = self._history + [{"who": who, "text": text}]
        self.historyChanged.emit()

    def run_js(self, script: str, callback):
        request_id = next(self._js_ids)
        self._js_callbacks[request_id] = callback
        self.runJs.emit(request_id, script)

    # ---- commands from the socket ------------------------------------------------------

    def handle(self, msg: dict, reply):
        cmd = msg.get("cmd")
        try:
            if cmd == "ping":
                reply({"ok": True, "url": self.url, "title": self.title})
            elif cmd == "say":
                self.activity()
                self._instruction = str(msg.get("text", ""))
                self._copy_text = str(msg.get("copy") or copy_text_for(self._instruction))
                self.instructionChanged.emit()
                self.set_status("Waiting for you…", "waiting")
                self._add_history("claude", self._instruction)
                element = int(msg.get("element") or 0)
                if element:
                    self.run_js(
                        HIGHLIGHT_JS.replace("%ID%", str(element)),
                        lambda found: reply({"ok": True, "highlighted": bool(found)}),
                    )
                else:
                    self.run_js(HIGHLIGHT_JS.replace("%ID%", "0"), lambda _: None)
                    reply({"ok": True})
            elif cmd == "read":
                self.activity()
                if self._status_kind != "waiting":
                    self.set_status("Claude is reading the page…", "working")

                def got(page):
                    if not isinstance(page, dict):
                        reply({"ok": False, "error": "page could not be read"})
                        return
                    items = page.pop("items", [])
                    text = pagetext.format_page({**page, "items": items}, full=bool(msg.get("full")))
                    page["text"] = protocol.truncate_page(text)
                    reply({"ok": True, "page": page})

                self.run_js(READ_JS, got)
            elif cmd == "wait":
                if self._waiter:  # a newer wait replaces the old one
                    self._flush_waiter(timed_out=True)
                timer = QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(lambda: self._flush_waiter(timed_out=True))
                self._waiter = (reply, timer)
                timer.start(int(float(msg.get("timeout", 50)) * 1000))
                self._flush_waiter()
            elif cmd == "navigate":
                self.activity()
                self.set_status("Claude is opening a page…", "working")
                self.navigateRequested.emit(normalize_url(str(msg.get("url", ""))))
                reply({"ok": True})
            elif cmd == "close":
                reply({"ok": True})
                self.end_session("closed_by_claude")
            else:
                reply({"ok": False, "error": f"unknown command: {cmd!r}"})
        except (TypeError, ValueError) as exc:
            reply({"ok": False, "error": str(exc)})


class Server(QObject):
    """Local socket server: reads one JSON line per connection and replies once."""

    def __init__(self, backend: Backend, path: Path):
        super().__init__()
        self.backend = backend
        self.path = path
        self.server = QLocalServer(self)
        QLocalServer.removeServer(str(path))
        if not self.server.listen(str(path)):
            raise RuntimeError(f"cannot listen on {path}: {self.server.errorString()}")
        self.server.newConnection.connect(self._accept)

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            buf = bytearray()
            sock.readyRead.connect(lambda s=sock, b=buf: self._read(s, b))

    def _read(self, sock: QLocalSocket, buf: bytearray):
        buf.extend(bytes(sock.readAll()))
        if b"\n" not in buf:
            return
        line = bytes(buf).split(b"\n", 1)[0]
        buf.clear()
        replied = False

        def reply(msg: dict):
            nonlocal replied
            if replied or sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
                return
            replied = True
            sock.write(protocol.encode(msg))
            sock.flush()
            sock.disconnectFromServer()

        try:
            msg = protocol.decode(line)
        except ValueError as exc:
            reply({"ok": False, "error": f"bad request: {exc}"})
            return
        self.backend.handle(msg, reply)

    def close(self):
        self.server.close()
        QLocalServer.removeServer(str(self.path))


class InputWatcher(QObject):
    """Any key press / click / scroll in the app counts as progress."""

    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend

    def eventFilter(self, obj, event):
        if event.type() in INPUT_EVENTS:
            self.backend.activity()
        return False


def create_profile(profile_dir: Path, parent: QObject) -> QQuickWebEngineProfile:
    """A persistent browser profile: cookies, logins and passed captchas survive restarts."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile = QQuickWebEngineProfile(parent)
    profile.setStorageName("borrowed-hands")
    profile.setOffTheRecord(False)
    profile.setPersistentStoragePath(str(profile_dir))
    profile.setCachePath(str(profile_dir / "cache"))
    # Keep session cookies too (cookie consent, carts), like a browser that restores tabs.
    profile.setPersistentCookiesPolicy(QQuickWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    # The default user agent says "QtWebEngine", which some sites block.
    profile.setHttpUserAgent(re.sub(r"QtWebEngine/\S+\s*", "", profile.httpUserAgent()))
    return profile


def create_window(engine: QQmlApplicationEngine, backend: Backend, url: str, profile_dir: Path):
    ctx = engine.rootContext()
    profile = create_profile(profile_dir, engine)
    ctx.setContextProperty("webProfile", profile)
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("startUrl", normalize_url(url))
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("failed to load Main.qml")
    return engine.rootObjects()[0]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    url = argv[0] if argv else "about:blank"

    QtWebEngineQuick.initialize()
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Borrowed Hands")
    app.setDesktopFileName("borrowed-hands")

    import os

    backend = Backend(
        idle_limit=float(os.environ.get("HANDS_IDLE_LIMIT", 120)),
        prompt_limit=float(os.environ.get("HANDS_PROMPT_LIMIT", 60)),
    )
    server = Server(backend, paths.socket_path())
    engine = QQmlApplicationEngine()
    window = create_window(engine, backend, url, paths.data_dir() / "profile")
    # Filter on the window, not the app: an app-wide Python event filter crashes PySide
    # when it sees objects that are still being constructed.
    watcher = InputWatcher(backend)
    window.installEventFilter(watcher)
    # Give a pending `wait` a moment to receive session_ended before quitting.
    backend.closeRequested.connect(lambda: QTimer.singleShot(200, app.quit))

    code = app.exec()
    server.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
