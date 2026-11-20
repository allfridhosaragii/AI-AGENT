"""Node revise (T7): satu iterasi perbaikan atas temuan.

Bila tidak ada temuan: tandai selesai (``status="done"``,
``approved_commit=True``). Bila masih ada temuan: naikkan
``fix_iterations`` / ``total_iterations`` dan kembali ke audit;
edge ``should_revise`` yang memutuskan eskalasi bila berulang.
"""

from __future__ import annotations

try:
    from .common import append_message
except ImportError:  # pragma: no cover
    from common import append_message  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Revisi -> patch state."""
    findings = getattr(state, "findings", []) or []
    if not findings:
        messages = append_message(
            state, "reviser", "Tidak ada temuan tersisa; siap commit.")
        return {"messages": messages, "phase": "done", "status": "done",
                "approved_commit": True}
    messages = append_message(
        state, "reviser",
        f"Perbaiki {len(findings)} temuan (iterasi "
        f"{getattr(state, 'fix_iterations', 0) + 1}).")
    return {"messages": messages, "phase": "audit",
            "fix_iterations": getattr(state, "fix_iterations", 0) + 1,
            "total_iterations": getattr(state, "total_iterations", 0) + 1}
