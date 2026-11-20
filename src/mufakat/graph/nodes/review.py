"""Node review (T7+T11): review kode oleh reviewer independen.

Review dilakukan DUA jalur:
1. Adapter ``review`` (bila ada): diminta menilai kode di worktree;
   bila teks review mengandung kata ``blocking``, satu temuan
   blocking dicatat.
2. Temuan gate yang sudah ada di ``ctx["gate_results"]`` disalin
   ke ``state.findings`` (bila ada).

Reviewer TIDAK menyetujui kodenya sendiri dan TIDAK menulis kode —
hanya menilai.
"""

from __future__ import annotations

from pathlib import Path

try:
    from .common import append_message, call_adapter
except ImportError:  # pragma: no cover
    from common import append_message, call_adapter  # type: ignore


def _as_dict(item):
    if isinstance(item, dict):
        return item
    return getattr(item, "__dict__", {}) or {}


async def node(state, adapters=None, ctx=None):
    """Review -> patch state."""
    ctx = ctx or {}
    worktree = ctx.get("worktree")
    code_text = ""
    if worktree:
        main_py = Path(worktree) / "main.py"
        try:
            code_text = main_py.read_text(encoding="utf-8")[:4000]
        except OSError:
            code_text = ""
    review_text = await call_adapter(
        adapters, "review",
        "Review: tidak ada temuan.",
        state)
    findings = [f for f in (getattr(state, "findings", []) or [])
                if f.get("tool") in ("research", "critique")]
    # Catatan: kata "blocking" di teks review = satu temuan blocking.
    # Teks mock/default TIDAK BOLEH mengandung kata itu kecuali
    # memang menandai temuan blocking (dulu: "tidak ada temuan
    # blocking." justru memicu temuan blocking di setiap run mock).
    if "blocking" in review_text.lower():
        findings.append({
            "tool": "review", "severity": "blocking", "file": "main.py",
            "line": 0, "rule": "review-blocking",
            "message": review_text[:300],
        })
    gate_results = ctx.get("gate_results") or []
    for result in gate_results:
        result = _as_dict(result)
        for finding in result.get("findings", []) or []:
            findings.append(dict(finding))
    if gate_results:
        text = f"Review selesai: {len(findings)} temuan dari gates."
    else:
        text = (f"Review selesai: {review_text[:200]} "
                f"(kode ditinjau: {len(code_text)} karakter).")
    messages = append_message(state, "reviewer", text)
    return {"messages": messages, "findings": findings, "phase": "audit"}
