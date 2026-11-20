"""Node research (T7): riset awal atas ide pengguna.

Tanpa adapter: hasil riset dummy deterministik berbahasa Indonesia.
Dengan adapter ``adapters["research"]``: pakai teks dari adapter.
"""

from __future__ import annotations

try:
    from .common import append_message, call_adapter
except ImportError:  # pragma: no cover - dijalankan sebagai skrip langsung
    from common import append_message, call_adapter  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Riset ide -> patch state."""
    dummy = (
        "Riset awal untuk ide: '{idea}'. "
        "Temuan: (1) kebutuhan utama pengguna perlu dipetakan; "
        "(2) ada pendekatan sederhana yang sudah umum dipakai; "
        "(3) risiko utama adalah ruang lingkup yang melebar. "
        "Riset ini dihasilkan secara lokal tanpa memanggil API."
    ).format(idea=getattr(state, "idea", ""))
    text = await call_adapter(adapters, "research", dummy, state)
    messages = append_message(state, "researcher", text)
    findings = list(getattr(state, "findings", []) or [])
    findings.append({
        "tool": "research", "severity": "info",
        "file": "", "line": 0, "rule": "riset-awal",
        "message": "Riset awal selesai: kebutuhan, pendekatan, dan risiko terpetakan.",
    })
    return {"messages": messages, "findings": findings, "phase": "debate"}
