"""Node review (T7): review kode; isi findings dari gates bila ada.

Bila ``ctx["gate_results"]`` tersedia (daftar GateResult/dict),
temuan dari gate disalin ke ``state.findings``. Bila tidak ada,
findings dikosongkan dari temuan gate (temuan riset/kritik tetap).
"""

from __future__ import annotations

try:
    from .common import append_message
except ImportError:  # pragma: no cover
    from common import append_message  # type: ignore


def _as_dict(item):
    if isinstance(item, dict):
        return item
    return getattr(item, "__dict__", {}) or {}


async def node(state, adapters=None, ctx=None):
    """Review -> patch state."""
    gate_results = (ctx or {}).get("gate_results") or []
    findings = [f for f in (getattr(state, "findings", []) or [])
                if f.get("tool") in ("research", "critique")]
    for result in gate_results:
        result = _as_dict(result)
        for finding in result.get("findings", []) or []:
            findings.append(dict(finding))
    if gate_results:
        text = f"Review selesai: {len(findings)} temuan dari gates."
    else:
        text = "Review selesai: tidak ada temuan gate (tidak ada gate dijalankan)."
    messages = append_message(state, "reviewer", text)
    return {"messages": messages, "findings": findings, "phase": "audit"}
