"""Talks to the window over its local socket; starts the window when needed.

No Qt here, so the MCP server and the CLI stay light.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from borrowed_hands import paths, protocol


class NotRunning(Exception):
    """The window is not open (never started, or the session ended)."""


def request(msg: dict, timeout: float = 10.0, sock_path: Path | None = None) -> dict:
    sock_path = sock_path or paths.socket_path()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        try:
            s.connect(str(sock_path))
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            raise NotRunning(str(exc)) from exc
        s.sendall(protocol.encode(msg))
        buf = bytearray()
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    finally:
        s.close()
    if not buf:
        raise NotRunning("window closed the connection without replying")
    return protocol.decode(bytes(buf).split(b"\n", 1)[0])


def is_running() -> bool:
    try:
        return request({"cmd": "ping"}, timeout=2).get("ok", False)
    except (NotRunning, OSError, json.JSONDecodeError):
        return False


def open_window(url: str, start_timeout: float = 30.0) -> dict:
    """Open the window on url, or navigate the existing one."""
    if is_running():
        return request({"cmd": "navigate", "url": url})
    log_dir = paths.data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "window.log", "ab")
    subprocess.Popen(
        [sys.executable, "-m", "borrowed_hands.app", url],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        env=os.environ.copy(),
    )
    deadline = time.monotonic() + start_timeout
    while time.monotonic() < deadline:
        if is_running():
            return {"ok": True, "started": True}
        time.sleep(0.2)
    raise RuntimeError(f"window did not start within {start_timeout:.0f} s, see {log_dir / 'window.log'}")


def say(text: str, element: int | None = None, copy: str | None = None) -> dict:
    msg = {"cmd": "say", "text": text}
    if element:
        msg["element"] = element
    if copy:
        msg["copy"] = copy
    return request(msg)


def read(full: bool = False) -> dict:
    return request({"cmd": "read", "full": full}, timeout=30)


def wait(timeout: float = 50.0) -> dict:
    """Wait for progress. A closed window is reported as a session_ended event."""
    try:
        return request({"cmd": "wait", "timeout": timeout}, timeout=timeout + 10)
    except NotRunning:
        return {"ok": True, "status": "events", "events": [{"type": "session_ended", "reason": "window_not_open"}]}


def navigate(url: str) -> dict:
    return request({"cmd": "navigate", "url": url})


def close() -> dict:
    try:
        return request({"cmd": "close"})
    except NotRunning:
        return {"ok": True, "already_closed": True}
