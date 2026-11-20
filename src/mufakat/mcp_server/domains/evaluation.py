"""Domain evaluation — review, skor, bukti, persetujuan review.

Permission: ``write-sandbox`` untuk submit review/evaluasi,
``read`` untuk membaca. Review TIDAK otomatis menyetujui kode:
``review_approve`` hanya mencatat persetujuan reviewer atas satu
review yang sudah ada, dan merge/commit tetap butuh approval
terpisah (domain approval).
"""

from __future__ import annotations

import json

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import read_run, runs_dir, utcnow

from . import store

DOMAIN = "evaluation"

CONTRACTS = [
    {"name": "evaluation_submit", "description": "Simpan evaluasi (skor 0-1) satu run.",
     "permission": "write-sandbox", "scope": "evaluation"},
    {"name": "review_submit", "description": "Kirim review dengan severity dan bukti.",
     "permission": "write-sandbox", "scope": "evaluation"},
    {"name": "review_approve", "description": "Setujui satu review yang sudah ada.",
     "permission": "write-sandbox", "scope": "evaluation"},
    {"name": "review_list", "description": "Daftar review satu run.",
     "permission": "read", "scope": "evaluation"},
]

_VALID_SEVERITY = ("info", "minor", "major", "blocking")


def evaluation_submit(run_id: str, score: float, notes: str = "") -> dict:
    """Simpan evaluasi (skor 0–1) untuk satu run."""
    if not 0.0 <= score <= 1.0:
        return err("score harus di antara 0 dan 1.", run_id=run_id, score=score)
    info = read_run(run_id)
    if info is None:
        return err("Run tidak ditemukan.", run_id=run_id)
    record = {"run_id": run_id, "score": score, "notes": notes,
              "submitted_at": utcnow()}
    path = runs_dir() / run_id / "evaluation.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    store.evaluations[run_id] = record
    return ok(**record, path=str(path))


def review_submit(run_id: str, reviewer: str, severity: str,
                  text: str, evidence: str = "") -> dict:
    """Kirim review: severity (info/minor/major/blocking) + bukti."""
    if severity not in _VALID_SEVERITY:
        return err(f"severity harus salah satu dari {list(_VALID_SEVERITY)}.",
                   severity=severity)
    review_id = new_id("rev")
    record = {"review_id": review_id, "run_id": run_id, "reviewer": reviewer,
              "severity": severity, "text": text, "evidence": evidence,
              "status": "submitted", "created_at": utcnow()}
    store.reviews[review_id] = record
    return ok(**record)


def review_approve(review_id: str, approver: str = "") -> dict:
    """Setujui satu review yang sudah ada (bukan persetujuan merge)."""
    review = store.reviews.get(review_id)
    if review is None:
        return err("Review tidak ditemukan.", review_id=review_id)
    review["status"] = "approved"
    review["approver"] = approver
    return ok(**review)


def review_list(run_id: str) -> dict:
    """Daftar review satu run."""
    items = [v for v in store.reviews.values() if v.get("run_id") == run_id]
    return ok(run_id=run_id, count=len(items), items=items)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain evaluation ke ``mcp``."""
    for fn in (evaluation_submit, review_submit, review_approve, review_list):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
