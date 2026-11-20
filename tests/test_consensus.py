"""Test konsensus MUFAKAT (T6): mufakat / tidak mufakat / tie / sepakat palsu."""

from mufakat.consensus.anonymize import anonymize, deanonymize
from mufakat.consensus.voting import borda_count, decide, detect_false_consensus


def _votes(decisions):
    return [{"decision": d, "ranking": ["A", "B", "C"]} for d in decisions]


def test_mufakat_dua_pertiga_tanpa_blocking():
    r = decide(_votes(["approve", "approve", "revise"]), [])
    assert r["decision"] == "mufakat"
    assert r["approve_ratio"] == 2 / 3
    assert r["blocking"] == 0


def test_tidak_mufakat_karena_blocking():
    critiques = [{"severity": "blocking", "text": "SQL injection belum diperbaiki"}]
    r = decide(_votes(["approve", "approve", "approve"]), critiques)
    assert r["decision"] == "belum_mufakat"
    assert r["blocking"] == 1


def test_tidak_mufakat_karena_kurang_dua_pertiga():
    r = decide(_votes(["approve", "reject", "reject"]), [])
    assert r["decision"] == "belum_mufakat"


def test_tie_borda():
    rankings = [["A", "B"], ["B", "A"]]
    scores = borda_count(rankings)
    assert scores["A"] == scores["B"]
    r = decide(
        [{"decision": "approve", "ranking": ["A", "B"]},
         {"decision": "approve", "ranking": ["B", "A"]}],
        [],
    )
    # Seri Borda yang sesungguhnya — dulu test ini menerima "tie" ATAU
    # "mufakat" sehingga tie yang hilang tidak pernah ketahuan.
    assert r["decision"] == "tie"
    assert r["winner"] is None
    assert r["borda"]["A"] == r["borda"]["B"]


def test_borda_count_menang_jelas():
    scores = borda_count([["A", "B", "C"], ["A", "C", "B"], ["B", "A", "C"]])
    assert scores["A"] > scores["B"] > scores["C"]


def test_anonymize_deterministik_dengan_seed():
    proposals = [{"agent_id": "deepseek", "text": "pakai FastAPI"},
                 {"agent_id": "openrouter", "text": "pakai Flask"},
                 {"agent_id": "gemini", "text": "pakai Django"}]
    a1 = anonymize(proposals, seed=7)
    a2 = anonymize(proposals, seed=7)
    assert [p["label"] for p in a1] == [p["label"] for p in a2]
    assert {p["label"] for p in a1} == {"A", "B", "C"}
    assert "agent_id" not in a1[0]  # identitas asli disembunyikan
    assert deanonymize(a1.mapping, a1[0]["label"]) in {"deepseek", "openrouter", "gemini"}


def test_sepakat_palsu_terdeteksi():
    same = ["pakai FastAPI saja"] * 3
    assert detect_false_consensus(same)
    assert not detect_false_consensus(["pakai FastAPI", "pakai Flask", "pakai Django"])
