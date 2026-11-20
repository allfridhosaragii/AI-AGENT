"""Voting, Borda count and false-consensus detection (T6)."""

from __future__ import annotations

import difflib
from collections import Counter

try:  # Optional: protocol.py is owned by another subagent.
    from .protocol import MufakatMessage  # noqa: F401
except ImportError:  # pragma: no cover
    MufakatMessage = None  # type: ignore

APPROVE_THRESHOLD = 2 / 3


def borda_count(rankings: list[list[str]]) -> dict[str, int]:
    """Borda count over full/partial rankings.

    First place gets ``len(ranking) - 1`` points, second ``len - 2``,
    ..., last 0.  Partial rankings still score by position within
    that ranking.
    """
    scores: Counter[str] = Counter()
    for ranking in rankings:
        n = len(ranking)
        for position, candidate in enumerate(ranking):
            scores[candidate] += n - 1 - position
    return dict(scores)


def detect_false_consensus(texts: list[str]) -> bool:
    """True if every pair of texts is near-identical (>0.9 similarity).

    High pairwise similarity across all proposals suggests copy-paste /
    herd agreement rather than independent consensus.  Fewer than two
    texts cannot be a false consensus.
    """
    if len(texts) < 2:
        return False
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ratio = difflib.SequenceMatcher(None, texts[i], texts[j]).ratio()
            if ratio <= 0.9:
                return False
    return True


def decide(votes: list[dict], critiques: list[dict]) -> dict:
    """Decide the consensus outcome.

    ``votes``: ``[{"agent_id": ..., "decision": "approve"|"revise"|
    "reject", "ranking": [candidate, ...]}, ...]``
    ``critiques``: ``[{"severity": "blocking"|"major"|"minor", ...}, ...]``

    Returns ``{"decision": "mufakat"|"belum_mufakat"|"tie",
    "approve_ratio": float, "blocking": int, "borda": dict,
    "winner": str|None}``.
    """
    total = len(votes)
    approves = sum(1 for v in votes if v.get("decision") == "approve")
    approve_ratio = (approves / total) if total else 0.0
    blocking = sum(1 for c in critiques if c.get("severity") == "blocking")

    rankings = [v.get("ranking") or [] for v in votes if v.get("ranking")]
    borda = borda_count(rankings)

    winner: str | None = None
    decision = "belum_mufakat"
    if borda:
        top_score = max(borda.values())
        leaders = [c for c, s in borda.items() if s == top_score]
        if len(leaders) > 1:
            decision = "tie"
        else:
            winner = leaders[0]
    if decision != "tie":
        if approve_ratio >= APPROVE_THRESHOLD and blocking == 0:
            decision = "mufakat"
        else:
            decision = "belum_mufakat"

    return {
        "decision": decision,
        "approve_ratio": approve_ratio,
        "blocking": blocking,
        "borda": borda,
        "winner": winner,
    }
