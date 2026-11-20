"""Domain project — project, brief/konteks, ADR.

Permission: ``write-sandbox`` untuk membuat project/ADR,
``read`` untuk membaca konteks. Project di sini metadata
dalam-memori; run dan artefak proyek tetap di ``runs/<run_id>/``.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "project"

CONTRACTS = [
    {"name": "project_create", "description": "Buat project baru.",
     "permission": "write-sandbox", "scope": "projects"},
    {"name": "project_get_context", "description": "Baca konteks/brief satu project.",
     "permission": "read", "scope": "projects"},
    {"name": "project_create_adr", "description": "Catat Architecture Decision Record.",
     "permission": "write-sandbox", "scope": "projects"},
]


def project_create(name: str, description: str = "") -> dict:
    """Buat project baru."""
    project_id = new_id("proj")
    record = {"project_id": project_id, "name": name,
              "description": description, "status": "active",
              "adrs": [], "created_at": utcnow()}
    store.projects[project_id] = record
    return ok(**record)


def project_get_context(project_id: str) -> dict:
    """Baca konteks/brief satu project."""
    project = store.projects.get(project_id)
    if project is None:
        return err("Project tidak ditemukan.", project_id=project_id)
    return ok(**project)


def project_create_adr(project_id: str, title: str, decision: str,
                       context: str = "") -> dict:
    """Catat Architecture Decision Record (ADR) untuk satu project."""
    project = store.projects.get(project_id)
    if project is None:
        return err("Project tidak ditemukan.", project_id=project_id)
    adr = {"adr_id": new_id("adr"), "title": title, "decision": decision,
           "context": context, "created_at": utcnow()}
    project.setdefault("adrs", []).append(adr)
    return ok(project_id=project_id, **adr)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain project ke ``mcp``."""
    for fn in (project_create, project_get_context, project_create_adr):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
