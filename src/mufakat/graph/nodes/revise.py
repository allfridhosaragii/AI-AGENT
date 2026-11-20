"""Node revise (T7+T11): satu iterasi perbaikan nyata atas temuan.

Bila tidak ada temuan: tandai selesai (``status="done"``,
``approved_commit=True``). Bila masih ada temuan: coba perbaikan
nyata yang aman — jalankan ``ruff check --fix`` pada worktree
(hanya perbaikan lint otomatis, TIDAK menghapus/melemahkan test,
TIDAK menonaktifkan security check) — lalu hitung ulang
``diff_hash`` dan naikkan ``fix_iterations`` / ``total_iterations``.
Edge ``should_revise`` yang memutuskan eskalasi bila berulang.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from .common import append_message, sha256_text
except ImportError:  # pragma: no cover
    from common import append_message, sha256_text  # type: ignore


def _ruff_bin() -> str | None:
    """Lokasi binary ruff (PATH atau di samping python yang berjalan)."""
    found = shutil.which("ruff")
    if found:
        return found
    candidate = Path(sys.executable).parent / "ruff"
    return str(candidate) if candidate.is_file() else None


def _worktree_hash(worktree: str) -> str:
    combined = ""
    root = Path(worktree)
    for name in sorted(p.name for p in root.iterdir() if p.is_file()):
        try:
            combined += (root / name).read_text(encoding="utf-8")
        except OSError:
            continue
    return sha256_text(combined)


async def node(state, adapters=None, ctx=None):
    """Revisi -> patch state."""
    findings = getattr(state, "findings", []) or []
    if not findings:
        messages = append_message(
            state, "reviser", "Tidak ada temuan tersisa; siap commit.")
        return {"messages": messages, "phase": "done", "status": "done",
                "approved_commit": True}
    ctx = ctx or {}
    worktree = ctx.get("worktree")
    fixed = False
    ruff = _ruff_bin() if worktree else None
    if ruff:
        try:
            proc = subprocess.run(
                [ruff, "check", "--fix", str(worktree)],
                capture_output=True, text=True, timeout=120, shell=False)
            fixed = proc.returncode == 0
        except Exception:
            fixed = False
    diff_hash = getattr(state, "diff_hash", "")
    if worktree and fixed:
        diff_hash = _worktree_hash(worktree)
    messages = append_message(
        state, "reviser",
        f"Perbaiki {len(findings)} temuan (iterasi "
        f"{getattr(state, 'fix_iterations', 0) + 1}; "
        f"ruff --fix: {'berhasil' if fixed else 'tidak dijalankan/gagal'}).")
    return {"messages": messages, "phase": "audit",
            "diff_hash": diff_hash,
            "fix_iterations": getattr(state, "fix_iterations", 0) + 1,
            "total_iterations": getattr(state, "total_iterations", 0) + 1}
