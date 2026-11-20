"""Domain observability — status server, run, binary, dan API key.

Permission: ``read`` saja. Fungsi ini TIDAK PERNAH mengembalikan
nilai secret — hanya ada/tidak-nya variabel env dan binary.
"""

from __future__ import annotations

import os
import shutil

from mufakat.mcp_server.tools import ok
from mufakat.runner import list_runs, utcnow

DOMAIN = "observability"

CONTRACTS = [
    {"name": "observability_status", "description": "Status server MCP dan lingkungan.",
     "permission": "read", "scope": "observability"},
    {"name": "observability_list_runs", "description": "Daftar run terbaru.",
     "permission": "read", "scope": "observability"},
]


def observability_status() -> dict:
    """Status observabilitas server: jumlah run, binary, env (ada/tidak)."""
    runs = list_runs()
    return ok(server="mufakat", transport="stdio",
              runs_count=len(runs),
              latest_run=runs[0]["run_id"] if runs else None,
              binaries={name: shutil.which(name) is not None
                        for name in ("docker", "ruff", "pytest", "git")},
              api_keys_present={
                  name: bool(os.environ.get(name))
                  for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                               "DEEPSEEK_API_KEY")},
              checked_at=utcnow())


def observability_list_runs(limit: int = 10) -> dict:
    """Daftar run terbaru (maks. ``limit``)."""
    runs = list_runs()[: max(1, limit)]
    return ok(count=len(runs), runs=[
        {"run_id": r["run_id"], "status": r["status"],
         "idea": r.get("idea", ""), "created_at": r.get("created_at", "")}
        for r in runs])


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain observability ke ``mcp``."""
    for fn in (observability_status, observability_list_runs):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
