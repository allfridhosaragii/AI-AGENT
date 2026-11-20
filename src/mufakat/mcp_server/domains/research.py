"""Domain research — pencarian dan referensi.

Permission: ``read`` / ``write-sandbox``. Jujur: ``research_search``
belum terhubung ke sumber web apa pun (status ``not_connected``,
hasil kosong) — tidak ada klaim riset web. Referensi yang disimpan
lewat ``research_save_reference`` berasal dari sumber yang diberikan
owner secara eksplisit.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "research"

CONTRACTS = [
    {"name": "research_search", "description": "Pencarian riset (belum terhubung ke web).",
     "permission": "read", "scope": "research"},
    {"name": "research_save_reference", "description": "Simpan referensi/dokumentasi.",
     "permission": "write-sandbox", "scope": "research"},
    {"name": "research_list_references", "description": "Daftar referensi tersimpan.",
     "permission": "read", "scope": "research"},
]


def research_search(query: str) -> dict:
    """Pencarian riset — belum terhubung ke sumber web; kembalikan status."""
    return ok(query=query, results=[], status="not_connected",
              note="research_search belum terhubung ke sumber web. "
                   "Isi hasil pencarian dari sumber yang disetujui owner.")


def research_save_reference(title: str, url: str = "", notes: str = "") -> dict:
    """Simpan referensi/dokumentasi (judul + URL + catatan)."""
    if not title:
        return err("title wajib diisi.")
    ref_id = new_id("ref")
    record = {"reference_id": ref_id, "title": title, "url": url,
              "notes": notes, "created_at": utcnow()}
    store.references[ref_id] = record
    return ok(**record)


def research_list_references() -> dict:
    """Daftar referensi tersimpan."""
    items = list(store.references.values())
    return ok(count=len(items), items=items)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain research ke ``mcp``."""
    for fn in (research_search, research_save_reference,
               research_list_references):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
