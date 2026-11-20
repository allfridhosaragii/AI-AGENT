"""Helper bersama untuk node graph MUFAKAT (T7).

Node TIDAK boleh memanggil API nyata bila adapter tidak ada: semua
teks dummy di sini deterministik dan berbahasa Indonesia. Voting dan
anonymize diimpor dari modul consensus (T6) bila tersedia, dengan
fallback lokal bila belum ada.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect

try:  # Modul consensus (T6) — beberapa jalur impor yang mungkin.
    from mufakat.consensus.voting import borda_count as _borda_count
    from mufakat.consensus.voting import decide as _consensus_decide
except ImportError:  # pragma: no cover
    try:
        from mufakat.consensus.voting import borda_count as _borda_count  # type: ignore
        from mufakat.consensus.voting import decide as _consensus_decide  # type: ignore
    except ImportError:
        _consensus_decide = None  # type: ignore[assignment]
        _borda_count = None  # type: ignore[assignment]

try:
    from mufakat.consensus.anonymize import anonymize as _anonymize
except ImportError:  # pragma: no cover
    try:
        from mufakat.consensus.anonymize import anonymize as _anonymize  # type: ignore
    except ImportError:
        _anonymize = None  # type: ignore[assignment]


# ---------------------------------------------------------------- fallback
def _fallback_decide(votes, critiques):
    total = len(votes) or 1
    approves = sum(1 for v in votes if v.get("decision") == "approve")
    ratio = approves / total
    blocking = sum(1 for c in critiques if c.get("severity") == "blocking")
    winner = None
    if votes:
        winner = max(votes, key=lambda v: len(v.get("ranking") or [])).get(
            "ranking", [None]
        )[0]
    decision = "mufakat" if ratio >= 2 / 3 and blocking == 0 else "belum_mufakat"
    return {"decision": decision, "approve_ratio": ratio,
            "blocking": blocking, "borda": {}, "winner": winner}


def decide_votes(votes, critiques):
    """Voting konsensus (modul T6 bila ada, fallback lokal bila belum)."""
    if _consensus_decide is not None:
        return _consensus_decide(votes, critiques)
    return _fallback_decide(votes, critiques)


def anonymize_proposals(proposals, seed=42):
    """Anonimisasi proposal (modul T6 bila ada, fallback lokal)."""
    if _anonymize is not None:
        return _anonymize(proposals, seed=seed)
    out, mapping = [], {}
    for i, p in enumerate(proposals):
        label = chr(ord("A") + i)
        mapping[label] = p.get("agent_id", "")
        clean = {k: v for k, v in p.items() if k != "agent_id"}
        clean["label"] = label
        out.append(clean)
    out = list(out)
    return out  # fallback: tanpa atribut mapping


# ---------------------------------------------------------------- adapter
async def call_adapter(adapters, key, default_text, state=None):
    """Panggil adapter ``adapters[key]`` bila ada; bila tidak, kembalikan teks dummy.

    Adapter boleh berupa callable (sync/async) atau objek dengan method
    ``generate``/``run``. Tidak pernah memanggil API nyata sendiri.
    """
    fn = (adapters or {}).get(key) if isinstance(adapters, dict) else None
    if fn is None:
        return default_text
    target = getattr(fn, "generate", getattr(fn, "run", fn))
    try:
        result = target(state) if state is not None else target()
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except Exception:
        return default_text


def append_message(state, role, content):
    messages = list(getattr(state, "messages", []) or [])
    messages.append({"role": role, "content": content})
    return messages


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _noop():  # pragma: no cover
    await asyncio.sleep(0)
