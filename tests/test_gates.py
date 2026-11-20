"""Test gates MUFAKAT (T10-T11, diperbaiki audit 20 Nov 2026: C1+H3+H4).

Repo contoh berisi secret palsu + SQL injection + test gagal HARUS
menghasilkan verdict TIDAK AMAN dengan 3 kategori
(secret, sql-injection, test-gagal). Repo bersih HARUS AMAN.

Semua gate jalan HANYA lewat sandbox Docker. Karena Docker tidak
tersedia di semua mesin, test memakai ``fake_sandbox_runner`` —
simulasi sandbox yang tool-nya lengkap: pytest/bandit/ruff dijalankan
sungguhan di host (hanya oleh test ini), sedangkan semgrep/gitleaks/
trivy yang tidak terpasang di host diemulasikan dari pola regex repo
sendiri (emulasi ini HANYA ada di test — kode produksi tidak pernah
memakai regex sebagai pengganti tool). Tanpa fake runner (Docker
tidak ada), semua gate HARUS gagal-tertutup ``sandbox-unavailable``
dan verdict ``BELUM_TERVERIFIKASI``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from mufakat.gates import bandit as bandit_gate
from mufakat.gates import gitleaks as gitleaks_gate
from mufakat.gates import pytest as pytest_gate
from mufakat.gates import semgrep as semgrep_gate
from mufakat.gates.runner import run_all
from mufakat.gates.verdict import verdict
from mufakat.sandbox.docker import docker_available

BAD_APP = '''"""Contoh repo bermasalah (sengaja dibuat untuk test)."""
import sqlite3

API_KEY = "AKIAIOSFODNN7EXAMPLE"


def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = " + user_id).fetchone()


def run_it(data):
    import pickle

    return pickle.loads(data)


def run_shell(cmd):
    import subprocess

    return subprocess.run(cmd, shell=True)


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


def get_user(conn, user_id: int):
    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()
'''

GOOD_TEST = '''"""Test contoh yang lolos."""
import sqlite3

from app import get_user


def test_get_user_tidak_ada():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    assert get_user(conn, 1) is None
'''


def _write(path, name, content):
    (path / name).write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fake sandbox runner (HANYA untuk test — lihat docstring modul).
# ---------------------------------------------------------------------------
def _emulate_semgrep(workdir: str) -> dict:
    from mufakat.gates._scan import scan_patterns

    findings = scan_patterns(Path(workdir), semgrep_gate._PATTERNS,
                             extensions={".py", ".js", ".ts"})
    results = [{
        "path": f["file"], "start": {"line": f["line"]},
        "check_id": f["rule"],
        "extra": {"severity": "ERROR" if f["severity"] == "HIGH" else "WARNING",
                  "message": f["message"]},
    } for f in findings]
    return {"exit_code": 0, "stdout": json.dumps({"results": results}),
            "stderr": "", "sandbox_unavailable": False}


def _emulate_gitleaks(workdir: str) -> dict:
    from mufakat.gates._scan import scan_patterns

    findings = scan_patterns(Path(workdir), gitleaks_gate._PATTERNS)
    items = [{"File": f["file"], "StartLine": f["line"],
              "RuleID": f["rule"], "Description": f["message"]}
             for f in findings]
    return {"exit_code": 1 if items else 0, "stdout": json.dumps(items),
            "stderr": "", "sandbox_unavailable": False}


def fake_sandbox_runner(image, workdir, command, timeout=300,
                        network_none=True, read_only=False,
                        extra_volumes=None, **_kwargs) -> dict:
    """Simulasi sandbox ber-tool lengkap (hanya untuk test).

    ``extra_volumes`` (N4): mount ``(host, container)`` — direktori
    host dibuat, lalu path container di perintah ditulis ulang ke
    path host (emulasi mount Docker: gate pytest menulis coverage
    ke ``/out/coverage.json`` di container).
    """
    command = str(command)
    for volume in extra_volumes or []:
        if isinstance(volume, (list, tuple)):
            host_path, container_path = str(volume[0]), str(volume[1])
        else:
            host_path, container_path = str(volume).split(":", 1)
        Path(host_path).mkdir(parents=True, exist_ok=True)
        command = command.replace(container_path + "/", host_path + "/")
    if "semgrep" in command and shutil.which("semgrep") is None:
        return _emulate_semgrep(str(workdir))
    if "gitleaks" in command and shutil.which("gitleaks") is None:
        return _emulate_gitleaks(str(workdir))
    if "trivy" in command and shutil.which("trivy") is None:
        return {"exit_code": 0, "stdout": json.dumps({"Results": []}),
                "stderr": "", "sandbox_unavailable": False}
    cmd = command.replace("python -m pytest",
                          f"{sys.executable} -m pytest")
    # Tool (bandit/ruff/pytest) hidup di direktori yang sama dengan
    # interpreter test — masukkan ke PATH supaya `command -v` di
    # perintah gate menemukannya (seperti di dalam image sandbox).
    import os

    env = dict(os.environ)
    bin_dir = str(Path(sys.executable).parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    result = subprocess.run(cmd, shell=True, cwd=str(workdir),
                            capture_output=True, text=True, timeout=timeout,
                            env=env)
    return {"exit_code": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "sandbox_unavailable": False}


# ---------------------------------------------------------------------------
# Test perilaku gate (dengan sandbox simulasi)
# ---------------------------------------------------------------------------
def test_repo_buruk_tidak_aman_tiga_kategori(tmp_path):
    """Secret + SQLi + test gagal -> TIDAK AMAN, 3 kategori."""
    _write(tmp_path, "app.py", BAD_APP)
    _write(tmp_path, "config.py", BAD_CONFIG)
    _write(tmp_path, "test_app.py", BAD_TEST)

    results = run_all(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert len(results) == 6
    by_tool = {r.tool: r for r in results}
    assert by_tool["semgrep"].passed is False
    assert by_tool["bandit"].passed is False
    assert by_tool["gitleaks"].passed is False
    assert by_tool["pytest"].passed is False

    out = verdict(results)
    assert out["safe"] is False
    assert out["status"] == "TIDAK AMAN"
    # Tiga kategori wajib ada; kategori tambahan (lint PLR0133 di test
    # gagal, coverage rendah karena test gagal, keamanan-kode dari
    # bandit HIGH) juga benar adanya.
    assert {"secret", "sql-injection", "test-gagal"} <= set(out["categories"])


def test_repo_bersih_aman(tmp_path):
    """Repo bersih (query berparameter + test lolos) -> AMAN."""
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)

    results = run_all(tmp_path, sandbox_runner=fake_sandbox_runner)
    out = verdict(results)
    assert out["safe"] is True
    assert out["status"] == "AMAN"
    assert out["categories"] == []


def test_coverage_nyata_terukur(tmp_path):
    """Gate pytest mengukur coverage nyata (bukan dari config)."""
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is True
    assert result.coverage is not None
    assert 0.0 <= result.coverage <= 1.0
    out = verdict([result])
    assert out["safe"] is True


def test_pytest_tanpa_test_gagal(tmp_path):
    """H3: tidak ada test untuk kode -> gate pytest GAGAL (fail-closed)."""
    _write(tmp_path, "app.py", GOOD_APP)
    result = pytest_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is False
    assert any(f["rule"] == "no-tests" for f in result.findings)


def test_bandit_medium_tidak_gagal_dan_b101_test_dikecualikan(tmp_path):
    """H4: bandit hanya gagal untuk HIGH/CRITICAL; B101 di test dikecualikan."""
    _write(tmp_path, "app.py",
           "import yaml\n\n\ndef load(text: str):\n"
           "    return yaml.load(text, Loader=yaml.Loader)\n")
    _write(tmp_path, "test_app.py",
           "from app import load\n\n\ndef test_load():\n"
           "    assert load('a: 1') == {'a': 1}\n")
    result = bandit_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result.passed is True  # hanya MEDIUM (B506) + B101 di test
    assert any(f["severity"] == "MEDIUM" for f in result.findings)
    assert not any(f["rule"] == "B101" for f in result.findings)
    # HIGH tetap menggagalkan (B602 subprocess shell=True = HIGH).
    _write(tmp_path, "evil.py",
           "import subprocess\n\n\ndef run(cmd):\n"
           "    return subprocess.run(cmd, shell=True)\n")
    result2 = bandit_gate.run(tmp_path, sandbox_runner=fake_sandbox_runner)
    assert result2.passed is False


# ---------------------------------------------------------------------------
# Test fail-closed tanpa Docker (C1 + H3) — PoC audit
# ---------------------------------------------------------------------------
def test_tanpa_docker_semua_gate_belum_terverifikasi(tmp_path):
    """Tanpa Docker: semua gate passed=False, verdict BELUM_TERVERIFIKASI."""
    if docker_available():
        return  # pragma: no cover - Docker ada di host ini
    _write(tmp_path, "app.py", GOOD_APP)
    _write(tmp_path, "test_app.py", GOOD_TEST)
    results = run_all(tmp_path)
    assert len(results) == 6
    assert all(r.passed is False for r in results)
    assert all(any(f["rule"] == "sandbox-unavailable" for f in r.findings)
               for r in results)
    out = verdict(results)
    assert out["safe"] is False
    assert out["status"] == "BELUM_TERVERIFIKASI"


def test_conftest_jahat_tidak_menyentuh_host(tmp_path):
    """C1 (PoC audit): conftest.py jahat tidak boleh membuat file di host.

    Tanpa Docker, gate pytest menolak berjalan (sandbox-unavailable)
    sehingga conftest tidak pernah dieksekusi di host.
    """
    if docker_available():
        return  # pragma: no cover - Docker ada di host ini
    marker = tmp_path.parent / "PWNED_pytest_gate"
    assert not marker.exists()
    _write(tmp_path, "test_app.py",
           "def test_ok():\n    assert True\n")
    _write(tmp_path, "conftest.py",
           f"from pathlib import Path\n"
           f"Path({str(marker)!r}).write_text('pwned')\n")
    result = pytest_gate.run(tmp_path)
    assert result.passed is False
    assert any(f["rule"] == "sandbox-unavailable" for f in result.findings)
    assert not marker.exists()

    # terminal_run pytest juga ditolak mentah-mentah (C1).
    from mufakat.mcp_server.tools import run_terminal_command

    denied = run_terminal_command(f"pytest {tmp_path}")
    assert denied["ok"] is False
    assert not marker.exists()
    # Domain testing juga menolak tanpa sandbox (conftest tetap dieksekusi
    # saat --collect-only, jadi tidak boleh jalan di host).
    from mufakat.mcp_server.domains.testing import testing_run

    assert testing_run(str(tmp_path))["ok"] is False
    assert not marker.exists()
