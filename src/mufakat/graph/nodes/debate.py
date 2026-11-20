"""Node debate (T7): tiga agen debat menghasilkan 3 proposal.

Tanpa adapter: 3 proposal dummy deterministik dari deepseek,
openrouter, dan gemini. Proposal dianonimisasi sebelum dinilai
(modul consensus T6 bila tersedia).
"""

from __future__ import annotations

try:
    from .common import anonymize_proposals, call_adapter
except ImportError:  # pragma: no cover
    from common import anonymize_proposals, call_adapter  # type: ignore

AGENTS = ("deepseek", "openrouter", "gemini")


async def node(state, adapters=None, ctx=None):
    """Debat -> 3 proposal (anonim) -> patch state."""
    idea = getattr(state, "idea", "")
    proposals = []
    for agent in AGENTS:
        dummy = (
            f"Proposal {agent}: bangun solusi untuk '{idea}' dengan "
            f"pendekatan {agent} — sederhana, teruji, dan mudah dirawat."
        )
        text = await call_adapter(adapters, f"debate_{agent}", dummy, state)
        proposals.append({"agent_id": agent, "text": text})
    anon = anonymize_proposals(proposals, seed=42)
    messages = list(getattr(state, "messages", []) or [])
    for item in anon:
        label = item.get("label", "?")
        messages.append({
            "role": "debater",
            "content": f"Proposal {label}: {item.get('text', '')}",
        })
    ctx = ctx or {}
    ctx["proposals"] = proposals
    ctx["anonymized_proposals"] = list(anon)
    return {"messages": messages, "phase": "critique"}
