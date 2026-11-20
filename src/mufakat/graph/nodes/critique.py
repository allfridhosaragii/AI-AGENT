"""Node critique (T7): kritik atas proposal debat.

Tanpa adapter: kritik dummy deterministik berbahasa Indonesia.
"""

from __future__ import annotations

try:
    from .common import append_message, call_adapter
except ImportError:  # pragma: no cover
    from common import append_message, call_adapter  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Kritik proposal -> patch state."""
    dummy = (
        "Kritik: (1) Proposal A paling sederhana tetapi kurang menangani "
        "kasus pinggir; (2) Proposal B paling lengkap tetapi paling mahal; "
        "(3) Proposal C seimbang, namun perlu penegasan ruang lingkup. "
        "Tidak ada kritik blocking; rekomendasi: lanjutkan Proposal C "
        "dengan penyederhanaan dari Proposal A."
    )
    text = await call_adapter(adapters, "critique", dummy, state)
    messages = append_message(state, "critic", text)
    findings = list(getattr(state, "findings", []) or [])
    findings.append({
        "tool": "critique", "severity": "minor",
        "file": "", "line": 0, "rule": "ruang-lingkup",
        "message": "Ruang lingkup proposal perlu ditegaskan sebelum spesifikasi ditulis.",
    })
    dissent = list(getattr(state, "dissent", []) or [])
    dissent.append("Proposal B dinilai terlalu mahal oleh kritikus.")
    return {"messages": messages, "findings": findings,
            "dissent": dissent, "phase": "meeting"}
