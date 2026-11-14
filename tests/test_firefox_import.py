"""Firefox cookie reading against a synthetic cookies.sqlite (no real Firefox needed)."""

import sqlite3

import pytest

from borrowed_hands import firefox_import


def make_db(path, rows):
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, originAttributes TEXT NOT NULL "
        "DEFAULT '', name TEXT, value TEXT, host TEXT, path TEXT, expiry INTEGER, "
        "lastAccessed INTEGER, creationTime INTEGER, isSecure INTEGER, isHttpOnly INTEGER, "
        "sameSite INTEGER DEFAULT 0)"
    )
    for r in rows:
        con.execute(
            "INSERT INTO moz_cookies (name, value, host, path, expiry, isSecure, isHttpOnly, "
            "sameSite) VALUES (?,?,?,?,?,?,?,?)",
            r,
        )
    con.commit()
    con.close()


ROWS = [
    # name, value, host, path, expiry, isSecure, isHttpOnly, sameSite
    ("sid", "abc", ".alza.cz", "/", 2000000000, 1, 1, 1),
    ("consent", "yes", "www.alza.cz", "/", 2000000000, 0, 0, 2),
    ("idn", "tok", "identity.alza.cz", "/", 2000000000, 1, 1, 1),
    ("other", "x", ".google.com", "/", 2000000000, 1, 0, 0),
    ("bank", "secret", ".mybank.cz", "/", 2000000000, 1, 1, 1),
]


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "cookies.sqlite"
    make_db(p, ROWS)
    return p


def test_reads_only_the_requested_domain_and_subdomains(db):
    cookies = firefox_import.read_cookies("alza.cz", db)
    hosts = sorted(c["host"] for c in cookies)
    assert hosts == [".alza.cz", "identity.alza.cz", "www.alza.cz"]
    assert all(c["host"] != ".google.com" for c in cookies)
    assert all("bank" not in c["name"] for c in cookies)


def test_cookie_fields_are_parsed(db):
    sid = next(c for c in firefox_import.read_cookies("alza.cz", db) if c["name"] == "sid")
    assert sid == {
        "name": "sid",
        "value": "abc",
        "host": ".alza.cz",
        "path": "/",
        "expiry": 2000000000,
        "secure": True,
        "http_only": True,
        "same_site": "lax",
    }


def test_domain_normalization(db):
    assert firefox_import.read_cookies("https://www.alza.cz/path", db)
    assert firefox_import.read_cookies(".alza.cz", db)


def test_subdomain_request_does_not_match_parent_siblings(db):
    cookies = firefox_import.read_cookies("identity.alza.cz", db)
    assert sorted(c["host"] for c in cookies) == ["identity.alza.cz"]


def test_no_cookies_for_unknown_domain_returns_empty(db):
    assert firefox_import.read_cookies("example.org", db) == []


def test_empty_domain_raises(db):
    with pytest.raises(firefox_import.FirefoxError):
        firefox_import.read_cookies("", db)


def test_reads_through_wal(tmp_path):
    """A row only in the -wal file is still read (we copy the WAL alongside)."""
    p = tmp_path / "cookies.sqlite"
    make_db(p, ROWS)
    con = sqlite3.connect(p)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "INSERT INTO moz_cookies (name, value, host, path, expiry, isSecure, isHttpOnly, "
        "sameSite) VALUES ('fresh','new','.alza.cz','/',2000000000,1,1,1)"
    )
    con.commit()  # stays in -wal until checkpoint
    assert (p.with_name(p.name + "-wal")).exists()
    names = {c["name"] for c in firefox_import.read_cookies("alza.cz", p)}
    con.close()
    assert "fresh" in names


def test_missing_database_raises():
    with pytest.raises(firefox_import.FirefoxError):
        firefox_import.read_cookies("alza.cz", "/nonexistent/path/cookies.sqlite")


def test_millisecond_expiry_is_normalized(tmp_path):
    p = tmp_path / "cookies.sqlite"
    make_db(p, [("s", "v", ".alza.cz", "/", 1825614272501, 1, 1, 1)])  # ms, as Firefox snap stores
    c = firefox_import.read_cookies("alza.cz", p)[0]
    assert 1_700_000_000 < c["expiry"] < 2_000_000_000  # back to a sane seconds value


def test_second_expiry_is_left_alone(tmp_path):
    p = tmp_path / "cookies.sqlite"
    make_db(p, [("s", "v", ".alza.cz", "/", 1825614272, 1, 1, 1)])  # already seconds
    assert firefox_import.read_cookies("alza.cz", p)[0]["expiry"] == 1825614272
