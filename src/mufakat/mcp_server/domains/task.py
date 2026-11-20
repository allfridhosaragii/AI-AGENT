"""Domain task — delegasi, assignment, status, dependency.

Permission: ``write-sandbox`` untuk membuat/mengubah task,
``read`` untuk membaca. Task hanya metadata; eksekusi task tetap
lewat graph/pipeline, bukan lewat tool ini.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "task"

CONTRACTS = [
    {"name": "task_create", "description": "Buat task baru di task board.",
     "permission": "write-sandbox", "scope": "tasks"},
    {"name": "task_assign", "description": "Tugaskan task ke satu agent.",
     "permission": "write-sandbox", "scope": "tasks"},
    {"name": "task_update_status", "description": "Ubah status task.",
     "permission": "write-sandbox", "scope": "tasks"},
    {"name": "task_get_dependencies", "description": "Daftar dependency satu task.",
     "permission": "read", "scope": "tasks"},
    {"name": "task_get", "description": "Baca satu task.",
     "permission": "read", "scope": "tasks"},
]

_VALID_STATUS = ("todo", "in_progress", "done", "blocked")


def task_create(title: str, project: str = "", assignee: str = "",
                depends_on: str = "") -> dict:
    """Buat task baru di task board."""
    task_id = new_id("task")
    record = {
        "task_id": task_id, "title": title, "project": project,
        "assignee": assignee, "status": "todo",
        "depends_on": [d.strip() for d in depends_on.split(",") if d.strip()],
        "created_at": utcnow(),
    }
    store.tasks[task_id] = record
    return ok(**record)


def task_assign(task_id: str, assignee: str) -> dict:
    """Tugaskan task ke satu agent."""
    task = store.tasks.get(task_id)
    if task is None:
        return err("Task tidak ditemukan.", task_id=task_id)
    task["assignee"] = assignee
    return ok(**task)


def task_update_status(task_id: str, status: str) -> dict:
    """Ubah status task (todo/in_progress/done/blocked)."""
    task = store.tasks.get(task_id)
    if task is None:
        return err("Task tidak ditemukan.", task_id=task_id)
    if status not in _VALID_STATUS:
        return err(f"status harus salah satu dari {list(_VALID_STATUS)}.",
                   status=status)
    task["status"] = status
    return ok(**task)


def task_get_dependencies(task_id: str) -> dict:
    """Daftar dependency satu task."""
    task = store.tasks.get(task_id)
    if task is None:
        return err("Task tidak ditemukan.", task_id=task_id)
    return ok(task_id=task_id, depends_on=list(task.get("depends_on", [])))


def task_get(task_id: str) -> dict:
    """Baca satu task."""
    task = store.tasks.get(task_id)
    if task is None:
        return err("Task tidak ditemukan.", task_id=task_id)
    return ok(**task)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain task ke ``mcp``."""
    for fn in (task_create, task_assign, task_update_status,
               task_get_dependencies, task_get):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
