"""Domain approval — permintaan dan status persetujuan (H1).

HANYA dua tool MCP: ``approval_request`` (minta) dan
``approval_get_status`` (baca). TIDAK ADA tool MCP yang bisa
memutuskan approval — ``approval_record_decision`` DIHAPUS dari
registrasi MCP (audit H1: AI bisa menyetujui commit-nya sendiri).

Keputusan HANYA dari manusia lewat CLI ``mufakat approve <id>``
(konfirmasi y/N di TTY), disimpan di SQLite
(:mod:`mufakat.mcp_server.approval_store`), terikat hash diff,
masa berlaku 24 jam, token sekali pakai. ``decide_approval`` di
bawah ini adalah fungsi internal untuk CLI — BUKAN tool MCP dan
TIDAK didaftarkan ke server.
"""

from __future__ import annotations

from mufakat.mcp_server import approval_store
from mufakat.mcp_server.tools import err, new_id, ok

DOMAIN = "approval"

CONTRACTS = [
    {"name": "approval_request", "description": "Minta persetujuan untuk keputusan/aksi.",
     "permission": "write-sandbox", "scope": "approvals"},
    {"name": "approval_get_status", "description": "Status satu approval.",
     "permission": "read", "scope": "approvals"},
]


def approval_request(title: str, run_id: str = "",
                     requested_by: str = "", diff_hash: str = "") -> dict:
    """Minta persetujuan (approval) untuk sebuah keputusan/aksi.

    Mencatat approval ``pending`` di SQLite. Keputusan TIDAK bisa
    dibuat lewat MCP — manusia menyetujui lewat ``mufakat approve``.
    """
    approval_id = new_id("appr")
    record = approval_store.create_approval(
        approval_id, title, run_id=run_id,
        requested_by=requested_by, diff_hash=diff_hash)
    return ok(**record)


def approval_get_status(approval_id: str) -> dict:
    """Status satu approval."""
    record = approval_store.get_approval(approval_id)
    if record is None:
        return err("Approval tidak ditemukan.", approval_id=approval_id)
    return ok(**record)


def decide_approval(approval_id: str, approved: bool,
                    decided_by: str = "", note: str = "",
                    diff_hash: str = "", repo_path: str = "",
                    branch: str = "", worktree: str = "") -> dict:
    """Putuskan approval — INTERNAL, hanya untuk CLI manusia.

    BUKAN tool MCP (tidak didaftarkan). Mengembalikan record +
    token sekali pakai bila disetujui. ``repo_path``/``branch``/
    ``worktree`` mengikat persetujuan ke identitas repo (GPT 3).
    """
    record, token = approval_store.decide_approval(
        approval_id, approved, decided_by=decided_by, note=note,
        diff_hash=diff_hash, repo_path=repo_path, branch=branch,
        worktree=worktree)
    if record is None:
        return err("Approval tidak ditemukan.", approval_id=approval_id)
    out = dict(record)
    if token is not None:
        out["approval_token"] = token
    return ok(**out)


def register(mcp) -> list[str]:
    """Daftarkan tool domain approval ke ``mcp`` (tanpa record_decision)."""
    for fn in (approval_request, approval_get_status):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
