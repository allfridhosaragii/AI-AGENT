"""Node revise (T7+T11, putaran 2: N11 + ruff di sandbox).

Bila tidak ada temuan: tandai selesai (``status="done"``,
``approved_commit=True``) — TAPI bila ``ctx`` meminta persetujuan
manusia, graph JEDA dulu lewat ``interrupt()`` (N11: approve commit)
dan ``approved_commit`` hanya True bila manusia menyetujui
(``Command(resume=True)``). Penolakan -> ``status="blocked"``,
``approved_commit=False``.

Bila masih ada temuan: coba perbaikan nyata yang aman — jalankan
``ruff check --fix`` pada worktree — lalu hitung ulang
``diff_hash`` dan naikkan ``fix_iterations`` / ``total_iterations``.
Edge ``should_revise`` yang memutuskan eskalasi bila berulang.

Ruff --fix TIDAK PERNAH jalan di host atas worktree AI (temuan
Rendah putaran 2): ia jalan DI DALAM sandbox Docker
(``mufakat.sandbox.docker.run_in_sandbox``, read-write mount,
``--network none``) — ruff tidak mengeksekusi kode, tapi tetap tidak
ada alasan menjalankannya di host. Tanpa Docker: tidak dijalankan
sama sekali (``fixed=False``), bukan fallback host.
"""

from __future__ import annotations

from pathlib import Path

try:
    from .common import append_message, resume_approved, sha256_text
except ImportError:  # pragma: no cover
    from common import append_message, resume_approved, sha256_text  # type: ignore


def _worktree_hash(worktree: str) -> str:
    combined = ""
    root = Path(worktree)
    for name in sorted(p.name for p in root.iterdir() if p.is_file()):
        try:
            combined += (root / name).read_text(encoding="utf-8")
        except OSError:
            continue
    return sha256_text(combined)


def _ruff_fix_in_sandbox(worktree: str, ctx: dict) -> bool:
    """Jalankan ``ruff check --fix`` atas worktree DI DALAM sandbox.

    ``ctx["sandbox_runner"]`` (hanya untuk test) menggantikan runner
    Docker asli; di produksi selalu ``None``. Mengembalikan True
    hanya bila ruff di dalam sandbox keluar 0. Tanpa Docker / ruff
    tidak ada di image -> False (tidak pernah fallback ke host).
    """
    try:
        from mufakat.sandbox.docker import SANDBOX_IMAGE, run_in_sandbox
    except ImportError:
        return False
    runner = ctx.get("sandbox_runner") or run_in_sandbox
    try:
        result = runner(
            SANDBOX_IMAGE, str(worktree),
            "command -v ruff >/dev/null 2>&1 || exit 127; "
            "ruff check --fix .",
            timeout=120, network_none=True, read_only=False)
    except Exception:
        return False
    if not isinstance(result, dict) or result.get("sandbox_unavailable"):
        return False
    return result.get("exit_code") == 0


async def node(state, adapters=None, ctx=None):
    """Revisi -> patch state."""
    findings = getattr(state, "findings", []) or []
    if not findings:
        # N11: titik approve commit — jeda untuk manusia bila diminta.
        # GraphInterrupt TIDAK ditangkap: ia harus naik ke Pregel
        # supaya graph benar-benar jeda.
        if (ctx or {}).get("require_human_approval"):
            try:
                from langgraph.types import interrupt
            except ImportError:
                interrupt = None  # type: ignore[assignment]
            if interrupt is not None:
                decision = interrupt({
                    "type": "approve_commit",
                    "diff_hash": getattr(state, "diff_hash", ""),
                    "message": "Setujui commit hasil revisi ini "
                               "(semua gate lolos, tidak ada temuan)."})
                if not resume_approved(decision):
                    messages = append_message(
                        state, "reviser",
                        "Commit DITOLAK manusia di titik approve — "
                        "tidak jadi commit.")
                    return {"messages": messages, "phase": "done",
                            "status": "blocked", "approved_commit": False}
        messages = append_message(
            state, "reviser", "Tidak ada temuan tersisa; siap commit.")
        return {"messages": messages, "phase": "done", "status": "done",
                "approved_commit": True}
    ctx = ctx or {}
    worktree = ctx.get("worktree")
    fixed = False
    if worktree:
        fixed = _ruff_fix_in_sandbox(str(worktree), ctx)
    diff_hash = getattr(state, "diff_hash", "")
    if worktree and fixed:
        diff_hash = _worktree_hash(worktree)
    messages = append_message(
        state, "reviser",
        f"Perbaiki {len(findings)} temuan (iterasi "
        f"{getattr(state, 'fix_iterations', 0) + 1}; "
        f"ruff --fix (sandbox): {'berhasil' if fixed else 'tidak dijalankan/gagal'}).")
    # M10: revisi kembali ke REVIEW (bukan langsung audit) — hasil
    # perbaikan harus direview manusia/agen dulu sebelum diaudit lagi.
    return {"messages": messages, "phase": "review",
            "diff_hash": diff_hash,
            "fix_iterations": getattr(state, "fix_iterations", 0) + 1,
            "total_iterations": getattr(state, "total_iterations", 0) + 1}
