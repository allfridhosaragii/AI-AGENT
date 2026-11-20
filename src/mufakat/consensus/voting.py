"""Voting, Borda count and false-consensus detection (T6)."""

from __future__ import annotations

import difflib
from collections import Counter

try:  # Optional: protocol.py is owned by another subagent.
    from .protocol import MufakatMessage  # noqa: F401
except ImportError:  # pragma: no cover
    MufakatMessage = None  # type: ignore

APPROVE_THRESHOLD = 2 / 3
VALID_DECISIONS = ("approve", "revise", "reject")


def _clean_ranking(ranking: object) -> list[str]:
    """Normalisasi satu ranking: hanya str, duplikat dibuang (kemunculan pertama).

    Ranking dari JSON impor tidak tepercaya bisa berisi string (``"ABC"``),
    duplikat (``["A", "A", "B"]`` — dulu memberi A poin ganda), atau
    elemen tak-hashable (dulu ``TypeError``). Semuanya dibersihkan di sini.
    """
    if isinstance(ranking, str):
        return []
    if not isinstance(ranking, (list, tuple)):
        return []
    seen: set[str] = set()
    clean: list[str] = []
    for candidate in ranking:
        if not isinstance(candidate, str) or not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        clean.append(candidate)
    return clean


def borda_count(rankings: list[list[str]]) -> dict[str, int]:
    """Borda count over full/partial rankings.

    First place gets ``len(ranking) - 1`` points, second ``len - 2``,
    ..., last 0.  Partial rankings still score by position within
    that ranking. Duplikat dalam satu ranking dihitung sekali.
    """
    scores: Counter[str] = Counter()
    for ranking in rankings:
        clean = _clean_ranking(ranking)
        n = len(clean)
        for position, candidate in enumerate(clean):
            scores[candidate] += n - 1 - position
    return dict(scores)


def detect_false_consensus(texts: list[str]) -> bool:
    """True if every pair of texts is near-identical (>0.9 similarity).

    High pairwise similarity across all proposals suggests copy-paste /
    herd agreement rather than independent consensus.  Fewer than two
    texts cannot be a false consensus. Teks kosong / hanya spasi tidak
    pernah dihitung sebagai sepakat palsu (dulu ``["", ""]`` -> True).
    """
    cleaned = [str(t).strip() for t in texts]
    if len(cleaned) < 2 or any(not t for t in cleaned):
        return False
    for i in range(len(cleaned)):
        for j in range(i + 1, len(cleaned)):
            ratio = difflib.SequenceMatcher(None, cleaned[i], cleaned[j]).ratio()
            if ratio <= 0.9:
                return False
    return True


def decide(votes: list[dict], critiques: list[dict]) -> dict:
    """Decide the consensus outcome.

    ``votes``: ``[{"agent_id": ..., "decision": "approve"|"revise"|
    "reject", "ranking": [candidate, ...]}, ...]``
    ``critiques``: ``[{"severity": "blocking"|"major"|"minor", ...}, ...]``

    Aturan yang diperbaiki (audit 20 Nov 2026):
    - Vote dengan ``decision`` di luar {approve, revise, reject} diabaikan
      (dulu ikut menekan ``approve_ratio`` sebagai penyebut).
    - Satu ``agent_id`` yang sama hanya dihitung sekali (vote pertama
      yang menang; impor ganda tidak lagi menggandakan suara).
    - Seri Borda (``tie``) tidak lagi menutupi ``blocking``: bila ada
      kritik blocking, keputusan tetap ``belum_mufakat``.

    Returns ``{"decision": "mufakat"|"belum_mufakat"|"tie",
    "approve_ratio": float, "blocking": int, "borda": dict,
    "winner": str|None}``.
    """
    seen_voters: set[str] = set()
    valid_votes: list[dict] = []
    for vote in votes:
        if not isinstance(vote, dict):
            continue
        if vote.get("decision") not in VALID_DECISIONS:
            continue
        voter = vote.get("agent_id")
        if isinstance(voter, str) and voter:
            if voter in seen_voters:
                continue
            seen_voters.add(voter)
        valid_votes.append(vote)

    total = len(valid_votes)
    approves = sum(1 for v in valid_votes if v.get("decision") == "approve")
    approve_ratio = (approves / total) if total else 0.0
    blocking = sum(
        1 for c in critiques
        if isinstance(c, dict) and c.get("severity") == "blocking"
    )

    rankings = [
        _clean_ranking(v.get("ranking")) for v in valid_votes if v.get("ranking")
    ]
    borda = borda_count(rankings)

    winner: str | None = None
    decision = "belum_mufakat"
    if borda:
        top_score = max(borda.values())
        leaders = [c for c, s in borda.items() if s == top_score]
        if len(leaders) > 1:
            # Seri hanya dilaporkan sebagai "tie" bila tidak ada blocking
            # dan rasio approve memenuhi ambang; bila tidak, blocking /
            # kurangnya approve yang menentukan (belum_mufakat).
            if blocking == 0 and approve_ratio >= APPROVE_THRESHOLD:
                decision = "tie"
            else:
                decision = "belum_mufakat"
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
