"""Domain filesystem — baca file aman + usulan patch (tanpa menulis).

Permission: ``read`` untuk baca, ``propose`` untuk usulan patch.
Tool ini TIDAK PERNAH menulis file: ``filesystem_propose_patch``
hanya mengembalikan usulan yang harus disetujui dan diterapkan
oleh pipeline/owner. File rahasia selalu ditolak.
"""

from __future__ import annotations

from pathlib import Path

from mufakat.mcp_server.tools import err, new_id, ok, read_file_safe
from mufakat.runner import utcnow

DOMAIN = "filesystem"

CONTRACTS = [
    {"name": "filesystem_read", "description": "Baca file teks (tolak file rahasia).",
     "permission": "read", "scope": "filesystem"},
    {"name": "filesystem_propose_patch",
     "description": "Usulkan patch untuk satu file (tidak menulis).",
     "permission": "propose", "scope": "filesystem"},
]

_SECRET_MARKERS = (".env", "secret", "credentials", ".pem", ".key",
                   "id_rsa", ".netrc")


def filesystem_read(path: str, allowed_roots=None) -> dict:
    """Baca file teks (allowlist folder workspace, tolak kredensial)."""
    return read_file_safe(path, allowed_roots=allowed_roots)


def filesystem_propose_patch(path: str, new_content: str,
                             reason: str = "", allowed_roots=None) -> dict:
    """Usulkan patch untuk satu file — TIDAK menulis file apa pun."""
    target = Path(path)
    if any(marker in target.name.lower() for marker in _SECRET_MARKERS):
        return err("File rahasia tidak boleh diubah lewat tool ini.",
                   path=target.name)
    current = read_file_safe(path, allowed_roots=allowed_roots)
    if not current.get("ok") and "tidak ditemukan" not in str(current.get("error", "")):
        # Di luar allowlist / symlink / kredensial: tolak usulan juga.
        return err(str(current.get("error", "File tidak bisa dibaca.")),
                   path=str(target))
    old_content = current.get("content", "") if current.get("ok") else ""
    return ok(patch_id=new_id("patch"), path=str(target),
              old_length=len(old_content), new_length=len(new_content),
              reason=reason, status="proposed",
              note="Patch HANYA usulan. Terapkan manual / lewat pipeline "
                   "setelah review, bukan lewat tool ini.",
              proposed_at=utcnow())


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain filesystem ke ``mcp``."""
    for fn in (filesystem_read, filesystem_propose_patch):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
