"""Domain memory — memori/knowledge per proyek.

Permission: ``read`` / ``write-sandbox``. Catatan: store ini
dalam-memori per proses server. Untuk persistensi, memori proyek
juga bisa disimpan lewat tabel ``project_memory`` di SQLite
(``mufakat.storage.db``) oleh runner — tool ini tidak mengklaim
persistensi antar-restart server.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "memory"

CONTRACTS = [
    {"name": "memory_write", "description": "Simpan catatan memori proyek.",
     "permission": "write-sandbox", "scope": "memory"},
    {"name": "memory_read", "description": "Baca catatan memori proyek.",
     "permission": "read", "scope": "memory"},
    {"name": "memory_list", "description": "Daftar catatan memori satu proyek.",
     "permission": "read", "scope": "memory"},
]


def memory_write(project_id: str, key: str, content: str) -> dict:
    """Simpan catatan memori proyek (key unik per proyek)."""
    if not project_id or not key:
        return err("project_id dan key wajib diisi.")
    record = {"memory_id": new_id("mem"), "project_id": project_id,
              "key": key, "content": content, "created_at": utcnow()}
    store.memories[f"{project_id}:{key}"] = record
    return ok(**record)


def memory_read(project_id: str, key: str) -> dict:
    """Baca catatan memori proyek berdasarkan key."""
    record = store.memories.get(f"{project_id}:{key}")
    if record is None:
        return err("Memori tidak ditemukan.", project_id=project_id, key=key)
    return ok(**record)


def memory_list(project_id: str) -> dict:
    """Daftar catatan memori satu proyek."""
    items = [v for k, v in store.memories.items()
             if k.startswith(f"{project_id}:")]
    return ok(project_id=project_id, count=len(items), items=items)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain memory ke ``mcp``."""
    for fn in (memory_write, memory_read, memory_list):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
