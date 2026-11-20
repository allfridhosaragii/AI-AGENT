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


def current_hash(state, findings=None) -> str:
    """Hash deterministik dari diff_hash + temuan saat ini.

    ``findings`` opsional: node ``test`` mengoper temuan yang baru
    dihitung (state lama belum memuatnya saat patch dibuat).
    """
    payload = json.dumps(
        {"diff": _get(state, "diff_hash", ""),
         "findings": findings if findings is not None
         else _get(state, "findings", [])},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def track_hash(state, h: str) -> bool:
    """Kembalikan True bila hash ``h`` sudah pernah dilihat.

    PURE-READ: riwayat dibaca dari ``state.hash_history`` saja.
    Riwayat DITULIS oleh node ``test`` (sebagai patch), BUKAN di
    sini — mutasi di dalam edge function LangGraph TIDAK disimpan
    ke checkpoint, sehingga pencatatan di edge selalu hilang
    antar-langkah (ditemukan 20 Nov 2026).
    """
    history = _get(state, "hash_history", None) or []
    return h in history


def _findings_not_decreasing(state) -> bool:
    """True bila jumlah temuan tidak turun selama 2 iterasi terakhir.

    PURE-READ: ``state.finding_counts`` ditulis oleh node ``test``
    (sebagai patch). Di sini hanya dibaca.
    """
    counts = list(_get(state, "finding_counts", []) or [])
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
    """``"revise"`` | ``"audit_final"`` | ``"escalate"``.

    PURE-READ: semua riwayat (``hash_history``, ``finding_counts``,
    ``fix_iterations``) ditulis oleh node sebagai patch; edge ini
    hanya membaca. Hash dianggap berulang bila muncul >= 2x di
    riwayat — node ``test`` sudah menambahkan hash iterasi saat ini,
    jadi 1x = baru, 2x = pernah dilihat di iterasi sebelumnya.
    """
    findings = _get(state, "findings", []) or []
    if not findings:
        return "audit_final"
    if _get(state, "fix_iterations", 0) >= MAX_FIX_ITERATIONS:
        return "escalate"
    if _get(state, "total_iterations", 0) >= MAX_TOTAL_ITERATIONS:
        return "escalate"
    history = _get(state, "hash_history", None) or []
    if history.count(current_hash(state)) >= 2:
        return "escalate"
    if _findings_not_decreasing(state):
        return "escalate"
    return "revise"
