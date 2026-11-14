"""Read cookies for ONE site from the user's Firefox profile (no Qt).

The per-site login import: the user logs in to a site in Firefox (where Google/Apple/… sign-in
works normally), then imports just that site's cookies into the Borrowed Hands browser so it is
logged in too.

Deliberately narrow:
- Only cookies whose host matches the requested domain (and its subdomains) are read.
- Saved passwords (logins.json / key4.db) are never opened. This copies an active session the
  user already created, not their stored credentials.
"""

import configparser
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

# Firefox stores sameSite as 0=None, 1=Lax, 2=Strict.
SAMESITE = {0: "none", 1: "lax", 2: "strict"}


class FirefoxError(Exception):
    """Firefox profile or cookie database could not be read."""


def firefox_user_agent() -> str | None:
    """A Firefox desktop User-Agent matching the installed version, or None if Firefox isn't
    found. Used to present the import window as the same browser that made the login, in case a
    site ties its session to the User-Agent."""
    try:
        out = subprocess.run(
            ["firefox", "--version"], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.\d+", out)
    if not match:
        return None
    major = match.group(1)
    return f"Mozilla/5.0 (X11; Linux x86_64; rv:{major}.0) Gecko/20100101 Firefox/{major}.0"


def _firefox_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".mozilla" / "firefox",  # system / deb
        home / "snap" / "firefox" / "common" / ".mozilla" / "firefox",  # snap
        home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",  # flatpak
    ]


def _profiles_from_ini(root: Path) -> list[Path]:
    """Profile dirs listed in profiles.ini, the default one first."""
    ini = root / "profiles.ini"
    if not ini.exists():
        return []
    parser = configparser.ConfigParser()
    try:
        parser.read(ini)
    except configparser.Error:
        return []
    profiles, default = [], None
    for section in parser.sections():
        if not section.lower().startswith("profile"):
            continue
        path = parser.get(section, "Path", fallback=None)
        if not path:
            continue
        is_relative = parser.get(section, "IsRelative", fallback="1") == "1"
        full = (root / path) if is_relative else Path(path)
        profiles.append(full)
        if parser.get(section, "Default", fallback="0") == "1":
            default = full
    if default in profiles:
        profiles.remove(default)
        profiles.insert(0, default)
    return profiles


def find_cookie_dbs() -> list[Path]:
    """All cookies.sqlite files we can find, most likely one first."""
    dbs: list[Path] = []
    for root in _firefox_roots():
        if not root.exists():
            continue
        candidates = _profiles_from_ini(root)
        if not candidates:  # no ini: fall back to scanning for profile dirs
            candidates = [p for p in root.glob("*.*") if p.is_dir()]
        for profile in candidates:
            db = profile / "cookies.sqlite"
            if db.exists() and db not in dbs:
                dbs.append(db)
    return dbs


def _normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    for prefix in ("http://", "https://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/")[0].split(":")[0]
    return domain.lstrip(".")


def _host_matches(host: str, domain: str) -> bool:
    host = host.lstrip(".").lower()
    return host == domain or host.endswith("." + domain)


def read_cookies(domain: str, db_path: Path | None = None) -> list[dict]:
    """Cookies for `domain` and its subdomains, from Firefox. Raises FirefoxError if the
    profile or database can't be read. Returns [] if the DB is fine but has no such cookies."""
    domain = _normalize_domain(domain)
    if not domain:
        raise FirefoxError("no domain given")

    if db_path is not None:
        dbs = [Path(db_path)]
    else:
        dbs = find_cookie_dbs()
        if not dbs:
            raise FirefoxError(
                "no Firefox cookie database found (looked in ~/.mozilla, snap and flatpak). "
                "Is Firefox installed and have you opened it at least once?"
            )

    last_error: Exception | None = None
    for db in dbs:
        try:
            cookies = _read_one(db, domain)
        except (OSError, sqlite3.Error) as exc:
            last_error = exc
            continue
        if cookies:
            return cookies
    if last_error is not None:
        raise FirefoxError(f"could not read Firefox cookies: {last_error}")
    return []


def _read_one(db: Path, domain: str) -> list[dict]:
    """Read one cookies.sqlite via a temp copy (so a running Firefox's lock/WAL is no problem)."""
    tmp = Path(tempfile.mkdtemp(prefix="hands-ffcookies-"))
    try:
        copy = tmp / "cookies.sqlite"
        shutil.copy2(db, copy)
        for suffix in ("-wal", "-shm"):
            extra = db.with_name(db.name + suffix)
            if extra.exists():
                shutil.copy2(extra, copy.with_name(copy.name + suffix))
        con = sqlite3.connect(copy)
        try:
            rows = con.execute(
                "SELECT name, value, host, path, expiry, isSecure, isHttpOnly, sameSite "
                "FROM moz_cookies"
            ).fetchall()
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    cookies = []
    for name, value, host, path, expiry, is_secure, is_http_only, same_site in rows:
        if not host or not _host_matches(host, domain):
            continue
        cookies.append(
            {
                "name": name or "",
                "value": value or "",
                "host": host,
                "path": path or "/",
                "expiry": _expiry_seconds(expiry),
                "secure": bool(is_secure),
                "http_only": bool(is_http_only),
                "same_site": SAMESITE.get(int(same_site or 0), "lax"),
            }
        )
    return cookies


def _expiry_seconds(expiry) -> int:
    """Expiry as a Unix time in seconds. Firefox usually stores seconds, but some builds (seen
    on the snap) store milliseconds; a plain seconds value won't reach 1e10 until the year 2286,
    so anything larger is milliseconds."""
    value = int(expiry or 0)
    if value > 10_000_000_000:
        value //= 1000
    return value
