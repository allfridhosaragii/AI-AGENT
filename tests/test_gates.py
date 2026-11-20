"""Test gates MUFAKAT (T10-T11).

Repo contoh berisi secret palsu + SQL injection + test gagal HARUS
menghasilkan verdict TIDAK AMAN dengan 3 kategori
(secret, sql-injection, test-gagal). Repo bersih HARUS AMAN.
"""

from __future__ import annotations

from mufakat.gates.runner import run_all
from mufakat.gates.verdict import verdict

BAD_APP = '''"""Contoh repo bermasalah (sengaja dibuat untuk test)."""
import sqlite3

API_KEY = "AKIAIOSFODNN7EXAMPLE"


def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = " + user_id).fetchone()


def connect():
    return sqlite3.connect(":memory:")
'''

BAD_CONFIG = '''# Konfigurasi contoh (secret palsu untuk test).
api_key = "AKIAIOSFODNN7EXAMPLE"
password = "contoh-sandi-palsu"
'''

BAD_TEST = '''"""Test contoh yang sengaja gagal."""


def test_contoh_gagal():
    assert 1 == 2, "contoh test gagal"
'''

GOOD_APP = '''"""Contoh repo bersih."""
import sqlite3


def get_user(conn, user_id: int):
    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()
'''

GOOD_TEST = '''"""Test contoh yang lolos."""
from app import get_user
import sqlite3


def test_get_user_tidak_ada():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    assert get_user(conn, 1) is None
'''


def _write(path, name, content):
    (path / name).write_text(content, encoding="utf-8")


def test_repo_buruk_tidak_aman_tiga_kategori(tmp_path):
    """Secret + SQLi + test gagal -> TIDAK AMAN, 3 kategori."""
    _write(tmp_path, "app.py", BAD_APP)
    _write(tmp_path, "config.py", BAD_CONFIG)
    _write(tmp_path, "test_app.py", BAD_TEST)

    results = run_all(tmp_path)
    assert len(results) == 6
    by_tool = {r.tool: r for r in results}
    assert by_tool["semgrep"].passed is False
    assert by_tool["bandit"].passed is False
    assert by_tool["gitleaks"].passed is False
    assert by_tool["pytest"].passed is False

    out = verdict(results)
    assert out["safe"] is False
    assert out["status"] == "TIDAK AMAN"
    assert set(out["categories"]) == {"secret", "sql-injection", "test-gagal"}


def test_repo_bersih_aman(tmp_path):
    """Repo bersih (query berparameter + test lolos) -> AMAN."""
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)

    results = run_all(tmp_path)
    out = verdict(results)
    assert out["safe"] is True
    assert out["status"] == "AMAN"
    assert out["categories"] == []
