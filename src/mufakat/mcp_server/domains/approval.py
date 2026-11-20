"""Domain approval — permintaan, status, dan keputusan persetujuan.

Permission: ``write-sandbox`` untuk meminta, ``approval-required``
untuk memutuskan (keputusan dicatat, bukan dieksekusi). Persetujuan
di sini adalah catatan; tindakan berisiko (commit/push/deploy)
tetap harus memeriksa catatan ini sebelum berjalan — lihat
domain git ``git_commit``.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "approval"

CONTRACTS = [
    {"name": "approval_request", "description": "Minta persetujuan untuk keputusan/aksi.",
     "permission": "write-sandbox", "scope": "approvals"},
    {"name": "approval_get_status", "description": "Status satu approval.",
     "permission": "read", "scope": "approvals"},
    {"name": "approval_record_decision", "description": "Catat keputusan approval.",
     "permission": "approval-required", "scope": "approvals"},
]


def approval_request(title: str, run_id: str = "",
                     requested_by: str = "") -> dict:
    """Minta persetujuan (approval) untuk sebuah keputusan/aksi."""
    approval_id = new_id("appr")
    record = {"approval_id": approval_id, "title": title, "run_id": run_id,
              "requested_by": requested_by, "status": "pending",
              "created_at": utcnow()}
    store.approvals[approval_id] = record
    return ok(**record)


def approval_get_status(approval_id: str) -> dict:
    """Status satu approval."""
    record = store.approvals.get(approval_id)
    if record is None:
        return err("Approval tidak ditemukan.", approval_id=approval_id)
    return ok(**record)


def approval_record_decision(approval_id: str, approved: bool,
                             note: str = "", decided_by: str = "") -> dict:
    """Catat keputusan approval (setujui/tolak) beserta catatan."""
    record = store.approvals.get(approval_id)
    if record is None:
        return err("Approval tidak ditemukan.", approval_id=approval_id)
    record["status"] = "approved" if approved else "rejected"
    record["note"] = note
    record["decided_by"] = decided_by
    record["decided_at"] = utcnow()
    return ok(**record)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain approval ke ``mcp``."""
    for fn in (approval_request, approval_get_status, approval_record_decision):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
