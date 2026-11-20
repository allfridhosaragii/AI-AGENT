"""Node meeting (T7): voting sederhana atas proposal.

Voting memakai modul consensus T6 (``decide``) bila tersedia, dengan
fallback lokal. Dummy deterministik: 2 dari 3 agen menyetujui
proposal pemenang sehingga tercapai mufakat (rasio 2/3).
"""

from __future__ import annotations

try:
    from .common import append_message, decide_votes
except ImportError:  # pragma: no cover
    from common import append_message, decide_votes  # type: ignore


async def node(state, adapters=None, ctx=None):
    """Voting mufakat -> patch state (approved_spec / round)."""
    proposals = (ctx or {}).get("proposals") or [
        {"agent_id": "deepseek", "text": "Proposal A"},
        {"agent_id": "openrouter", "text": "Proposal B"},
        {"agent_id": "gemini", "text": "Proposal C"},
    ]
    winner = proposals[0].get("text", "Proposal A")
    votes = [
        {"agent_id": "deepseek", "decision": "approve",
         "ranking": [winner, proposals[1].get("text", "Proposal B")]},
        {"agent_id": "openrouter", "decision": "approve",
         "ranking": [winner, proposals[2].get("text", "Proposal C")]},
        {"agent_id": "gemini", "decision": "revise",
         "ranking": [proposals[2].get("text", "Proposal C"), winner]},
    ]
    critiques = [c for c in (getattr(state, "findings", []) or [])
                 if c.get("tool") == "critique"]
    result = decide_votes(votes, critiques)
    decision = result.get("decision", "belum_mufakat")
    ratio = result.get("approve_ratio", 0.0)
    messages = append_message(
        state, "meeting",
        f"Voting selesai: keputusan={decision}, rasio setuju={ratio:.2f}, "
        f"pemenang={result.get('winner') or winner}.",
    )
    if decision == "mufakat":
        return {"messages": messages, "phase": "spec", "approved_spec": True}
    # Belum mufakat: naikkan ronde agar edge bisa eskalasi di ronde ke-3.
    return {"messages": messages, "phase": "debate",
            "round": getattr(state, "round", 1) + 1,
            "approved_spec": False}
