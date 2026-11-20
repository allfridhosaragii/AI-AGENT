"""Conditional edges MUFAKAT (T7).

Aturan eskalasi:
- Debat: lanjut selama ``round < 3`` dan belum mufakat; bila sudah
  mufakat -> ``"spec"``; bila ronde habis tanpa mufakat -> ``"escalate"``.
- Revisi: eskalasi bila hash (diff + temuan) berulang 2x, jumlah
  temuan tidak turun selama 2 iterasi, atau
  ``fix_iterations >= 5`` / ``total_iterations >= 12``.
"""

from __future__ import annotations

import hashlib
import json

MAX_DEBATE_ROUNDS = 3
MAX_FIX_ITERATIONS = 5
MAX_TOTAL_ITERATIONS = 12


def _get(state, key, default=None):
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)


def _set(state, key, value):
    if isinstance(state, dict):
        state[key] = value
    else:
        setattr(state, key, value)


def current_hash(state) -> str:
    """Hash deterministik dari diff_hash + temuan saat ini."""
    payload = json.dumps(
        {"diff": _get(state, "diff_hash", ""), "findings": _get(state, "findings", [])},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def track_hash(state, h: str) -> bool:
    """Catat hash ``h``; kembalikan True bila hash sudah pernah dilihat.

    Riwayat disimpan di ``state.hash_history`` (field RunState).
    """
    history = _get(state, "hash_history", None)
    if history is None:
        history = []
        _set(state, "hash_history", history)
    if h in history:
        return True
    history.append(h)
    return False


def _findings_not_decreasing(state) -> bool:
    """True bila jumlah temuan tidak turun selama 2 iterasi terakhir.

    Riwayat jumlah temuan disimpan di ``state.finding_counts``.
    """
    counts = list(_get(state, "finding_counts", []) or [])
    counts.append(len(_get(state, "findings", []) or []))
    _set(state, "finding_counts", counts)
    if len(counts) < 3:
        return False
    # Dua perbandingan terakhir: tidak ada penurunan sama sekali.
    return counts[-1] >= counts[-2] >= counts[-3]


def should_continue_debate(state) -> str:
    """``"debate"`` | ``"spec"`` | ``"escalate"``."""
    if _get(state, "approved_spec", False):
        return "spec"
    if _get(state, "round", 1) >= MAX_DEBATE_ROUNDS:
        return "escalate"
    return "debate"


def should_revise(state) -> str:
    """``"revise"`` | ``"audit_final"`` | ``"escalate"``."""
    findings = _get(state, "findings", []) or []
    if not findings:
        return "audit_final"
    if _get(state, "fix_iterations", 0) >= MAX_FIX_ITERATIONS:
        return "escalate"
    if _get(state, "total_iterations", 0) >= MAX_TOTAL_ITERATIONS:
        return "escalate"
    if track_hash(state, current_hash(state)):
        return "escalate"
    if _findings_not_decreasing(state):
        return "escalate"
    return "revise"
