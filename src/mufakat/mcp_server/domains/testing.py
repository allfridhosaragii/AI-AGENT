"""Domain testing — jalankan test dan baca hasilnya.

Permission: ``execute-approved`` untuk menjalankan pytest
(hanya perintah ``pytest`` yang dieksekusi, tanpa shell),
``read`` untuk membaca hasil gate yang tersimpan di
``runs/<run_id>/gates/``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from mufakat.mcp_server.tools import err, ok
from mufakat.runner import runs_dir

DOMAIN = "testing"

CONTRACTS = [
    {"name": "testing_run", "description": "pytest --collect-only (tanpa eksekusi test).",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_run_unit", "description": "Jalankan pytest -q pada satu target.",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_run_e2e", "description": "Jalankan test end-to-end di tests/e2e/.",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_get_results", "description": "Baca hasil gate test satu run.",
     "permission": "read", "scope": "testing"},
]


def testing_run(target: str = ".") -> dict:
    """Jalankan pytest --collect-only (aman, tanpa mengeksekusi test)."""
    if shutil.which("pytest") is None:
        return err("pytest tidak tersedia di lingkungan ini.", target=target)
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--collect-only", target],
            capture_output=True, text=True, timeout=120, shell=False)
    except subprocess.TimeoutExpired:
        return err("testing_run kehabisan waktu (timeout 120 detik).",
                   target=target)
    except Exception as exc:  # noqa: BLE001
        return err(f"Gagal menjalankan pytest: {exc}", target=target)
    tail = (proc.stdout + proc.stderr)[-20000:]
    return ok(target=target, returncode=proc.returncode,
              summary=tail.strip().splitlines()[-5:] if tail.strip() else [],
              output=tail)


def _run_pytest(target: str, timeout: int = 600) -> dict:
    if shutil.which("pytest") is None:
        return err("pytest tidak tersedia di lingkungan ini.", target=target)
    try:
        proc = subprocess.run(
            ["pytest", "-q", target], capture_output=True, text=True,
            timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return err("pytest kehabisan waktu.", target=target)
    except Exception as exc:  # noqa: BLE001
        return err(f"Gagal menjalankan pytest: {exc}", target=target)
    tail = (proc.stdout + proc.stderr)[-20000:]
    return ok(target=target, returncode=proc.returncode,
              passed=proc.returncode == 0, output=tail)


def test_run_unit(target: str = ".") -> dict:
    """Jalankan pytest -q pada satu target."""
    return _run_pytest(target)


def test_run_e2e(target: str = "tests/e2e") -> dict:
    """Jalankan test end-to-end di tests/e2e/ (HTTP TestClient)."""
    path = Path(target)
    if not path.is_dir():
        return err("Folder tests/e2e tidak ditemukan.", target=target)
    return _run_pytest(target)


def test_get_results(run_id: str) -> dict:
    """Baca hasil gate test satu run dari runs/<run_id>/gates/."""
    gates_dir = runs_dir() / run_id / "gates"
    if not gates_dir.is_dir():
        return err("Tidak ada hasil gate untuk run ini.", run_id=run_id)
    results = []
    for child in sorted(gates_dir.iterdir()):
        if child.is_file() and child.suffix == ".json":
            try:
                results.append(json.loads(child.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
    return ok(run_id=run_id, count=len(results), results=results)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain testing ke ``mcp``."""
    for fn in (testing_run, test_run_unit, test_run_e2e, test_get_results):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
