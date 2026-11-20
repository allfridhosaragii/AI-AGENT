"""Test anti-loop MUFAKAT (T11): hash osilasi + batas iterasi.

Aturan dari Claude §4 / BLUEPRINT §8: eskalasi bila hash
(diff + temuan) berulang 2x, jumlah temuan tidak turun selama
2 iterasi, fix_iterations >= 5, atau total_iterations >= 12.

PENTING (ditemukan 20 Nov 2026): ``should_revise`` adalah
PURE-READ. Riwayat ``hash_history`` / ``finding_counts`` ditulis
oleh node ``test`` sebagai patch — mutasi di dalam edge function
LangGraph tidak disimpan ke checkpoint, jadi pencatatan di edge
selalu hilang. Hash dianggap berulang bila muncul >= 2x di
riwayat (node test sudah menambahkan hash iterasi saat ini).
"""

from __future__ import annotations

from mufakat.graph.edges import (
    MAX_FIX_ITERATIONS,
    MAX_TOTAL_ITERATIONS,
    current_hash,
    should_revise,
    track_hash,
)
from mufakat.graph.state import RunState


def _state(**overrides):
    base = {"run_id": "test01", "idea": "ide tes"}
    base.update(overrides)
    return RunState(**base)


def test_tidak_ada_temuan_langsung_audit_final():
    state = _state(findings=[])
    assert should_revise(state) == "audit_final"


def test_hash_baru_lanjut_revisi():
    state = _state(findings=[{"tool": "pytest", "severity": "HIGH"}],
                   diff_hash="abc", hash_history=[])
    assert should_revise(state) == "revise"


def test_hash_osilasi_dua_kali_eskalasi():
    # Hash iterasi saat ini sudah dicatat node test (1x); bila hash
    # yang sama sudah ada dari iterasi sebelumnya (2x total) -> eskalasi.
    probe = _state(findings=[{"tool": "pytest", "severity": "HIGH"}],
                   diff_hash="abc")
    h = current_hash(probe)
    state = _state(findings=[{"tool": "pytest", "severity": "HIGH"}],
                   diff_hash="abc", hash_history=[h, h])
    assert should_revise(state) == "escalate"
    # Hanya 1x (hash baru, baru dicatat iterasi ini) -> lanjut revisi.
    state_baru = _state(findings=[{"tool": "pytest", "severity": "HIGH"}],
                        diff_hash="abc", hash_history=[h])
    assert should_revise(state_baru) == "revise"


def test_temuan_tidak_turun_dua_iterasi_eskalasi():
    state = _state(findings=[{"tool": "x"}, {"tool": "y"}],
                   diff_hash="d1", finding_counts=[2, 2, 2])
    assert should_revise(state) == "escalate"


def test_temuan_turun_lanjut_revisi():
    state = _state(findings=[{"tool": "x"}],
                   diff_hash="d1", finding_counts=[3, 2, 1])
    assert should_revise(state) == "revise"


def test_batas_fix_iterations_eskalasi():
    state = _state(findings=[{"tool": "x"}],
                   fix_iterations=MAX_FIX_ITERATIONS)
    assert should_revise(state) == "escalate"


def test_batas_total_iterations_eskalasi():
    state = _state(findings=[{"tool": "x"}],
                   total_iterations=MAX_TOTAL_ITERATIONS)
    assert should_revise(state) == "escalate"


def test_current_hash_deterministik():
    a = _state(findings=[{"tool": "x"}], diff_hash="d1")
    b = _state(findings=[{"tool": "x"}], diff_hash="d1")
    c = _state(findings=[{"tool": "y"}], diff_hash="d1")
    assert current_hash(a) == current_hash(b)
    assert current_hash(a) != current_hash(c)
    # Override findings: hash dihitung dari temuan yang dioper.
    assert current_hash(a, [{"tool": "y"}]) == current_hash(c)


def test_track_hash_pure_read_tidak_memutasi():
    state = _state(hash_history=["h1"])
    assert track_hash(state, "h1") is True
    assert track_hash(state, "h2") is False
    assert state.hash_history == ["h1"]
