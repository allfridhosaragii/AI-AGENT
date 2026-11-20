"""Domain testing — jalankan test dan baca hasilnya.

Permission: ``execute-approved`` untuk menjalankan pytest,
``read`` untuk membaca hasil gate yang tersimpan di
``runs/<run_id>/gates/``.

Audit C1: pytest TIDAK PERNAH dijalankan di host — semua eksekusi
test lewat sandbox Docker (:mod:`mufakat.sandbox.docker`). Tanpa
Docker, tool mengembalikan ``ok: False`` + status
``belum terverifikasi``. ``--collect-only`` pun tetap mengeksekusi
``conftest.py``, jadi ia juga wajib lewat sandbox.
"""

from __future__ import annotations

import json
from pathlib import Path

from mufakat.mcp_server.tools import err, ok
from mufakat.runner import runs_dir
from mufakat.sandbox.docker import SANDBOX_IMAGE, run_in_sandbox
from mufakat.sandbox.worktree import validate_run_id

DOMAIN = "testing"

CONTRACTS = [
    {"name": "testing_run",
     "description": "pytest --collect-only di sandbox (tanpa eksekusi test di host).",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_run_unit", "description": "Jalankan pytest -q di sandbox pada satu target.",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_run_e2e", "description": "Jalankan test end-to-end di tests/e2e/ (di sandbox).",
     "permission": "execute-approved", "scope": "testing"},
    {"name": "test_get_results", "description": "Baca hasil gate test satu run.",
     "permission": "read", "scope": "testing"},
]


def _sandbox_pytest(target: str, args: str, timeout: int = 600) -> dict:
    """Jalankan pytest di sandbox atas ``target`` (folder, di-mount /work)."""
    root = Path(target).resolve()
    if not root.exists():
        return err("Target test tidak ditemukan.", target=target)
    if root.is_file():
        workdir, rel = str(root.parent), root.name
    else:
        workdir, rel = str(root), "."
    result = run_in_sandbox(SANDBOX_IMAGE, workdir,
                            f"python -m pytest {args} {rel}",
                            timeout=timeout, network_none=True,
                            read_only=False)
    if result.get("sandbox_unavailable"):
        return err("Sandbox Docker tidak tersedia — test belum terverifikasi "
                   "(tidak dijalankan di host).",
                   target=target, verified=False,
                   status="BELUM_TERVERIFIKASI")
    tail = ((result.get("stdout") or "") + (result.get("stderr") or ""))[-20000:]
    return ok(target=target, returncode=result.get("exit_code"),
              passed=result.get("exit_code") == 0,
              verified=True, output=tail)


def testing_run(target: str = ".") -> dict:
    """Jalankan pytest --collect-only DI SANDBOX (conftest tetap dieksekusi)."""
    result = _sandbox_pytest(target, "-q --collect-only", timeout=120)
    if not result.get("ok"):
        return result
    tail = result.get("output", "")
    result["summary"] = tail.strip().splitlines()[-5:] if tail.strip() else []
    return result


def _run_pytest(target: str, timeout: int = 600) -> dict:
    return _sandbox_pytest(target, "-q", timeout=timeout)


def test_run_unit(target: str = ".") -> dict:
    """Jalankan pytest -q DI SANDBOX pada satu target."""
    return _run_pytest(target)


def test_run_e2e(target: str = "tests/e2e") -> dict:
    """Jalankan test end-to-end di tests/e2e/ (di sandbox)."""
    path = Path(target)
    if not path.is_dir():
        return err("Folder tests/e2e tidak ditemukan.", target=target)
    return _run_pytest(target)


def test_get_results(run_id: str) -> dict:
    """Baca hasil gate test satu run dari runs/<run_id>/gates/."""
    try:
        validate_run_id(run_id)
    except ValueError:
        return err("run_id tidak valid.", run_id=run_id)
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
