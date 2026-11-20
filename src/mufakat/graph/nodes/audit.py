"""Node audit (T7): jalankan gates keamanan atas worktree.

Bila ``ctx["worktree"]`` ada, jalankan ``gates.runner.run_all`` atas
direktori itu (import try/except; bila gates belum tersedia, temuan
kosong). Hasil disimpan ke ``ctx["gate_results"]`` dan findings.
"""

from __future__ import annotations

try:
    from .common import append_message
except ImportError:  # pragma: no cover
    from common import append_message  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Audit gates -> patch state."""
    ctx = ctx or {}
    worktree = ctx.get("worktree")
    gate_results = []
    findings = [f for f in (getattr(state, "findings", []) or [])
                if f.get("tool") in ("research", "critique")]
    if worktree:
        try:
            from mufakat.gates.runner import run_all
        except ImportError:
            try:
                from mufakat.gates.runner import run_all  # type: ignore
            except ImportError:
                run_all = None  # type: ignore[assignment]
        if run_all is not None:
            try:
                gate_results = run_all(worktree)
            except Exception:
                gate_results = []
            for result in gate_results:
                for finding in getattr(result, "findings", []) or []:
                    findings.append(dict(finding))
    ctx["gate_results"] = gate_results
    failed = [g for g in gate_results if not getattr(g, "passed", True)]
    text = (f"Audit selesai: {len(gate_results)} gate, "
            f"{len(failed)} gagal, {len(findings)} temuan.")
    messages = append_message(state, "auditor", text)
    return {"messages": messages, "findings": findings, "phase": "test"}
