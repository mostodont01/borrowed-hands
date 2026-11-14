"""Where the socket, profile and logs live. Overridable with env vars (used by tests)."""

import os
from pathlib import Path


def data_dir() -> Path:
    if env := os.environ.get("HANDS_DATA_DIR"):
        return Path(env)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "borrowed-hands"


def socket_path() -> Path:
    if env := os.environ.get("HANDS_SOCKET"):
        return Path(env)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return Path(runtime) / "borrowed-hands.sock"
    return Path(f"/tmp/borrowed-hands-{os.getuid()}.sock")
