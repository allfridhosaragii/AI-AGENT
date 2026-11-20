"""Domain terminal — eksekusi perintah allowlist saja.

Permission: ``execute-approved``. Hanya ``echo`` / ``ls`` yang
diizinkan, tanpa shell, tanpa metakarakter. ``pytest`` DIHAPUS dari
allowlist (audit C1): test hanya lewat gate sandbox. Perintah lain,
termasuk yang destruktif, ditolak mentah-mentah.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import run_terminal_command

DOMAIN = "terminal"

CONTRACTS = [
    {"name": "terminal_run",
     "description": "Jalankan perintah — HANYA echo, ls.",
     "permission": "execute-approved", "scope": "terminal"},
]


def terminal_run(command: str) -> dict:
    """Jalankan perintah terminal — HANYA echo, ls. Lainnya ditolak."""
    return run_terminal_command(command)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain terminal ke ``mcp``."""
    mcp.tool(terminal_run)
    return [c["name"] for c in CONTRACTS]
