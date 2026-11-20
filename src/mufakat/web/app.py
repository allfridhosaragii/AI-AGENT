"""Dashboard web MUFAKAT (T15, FastAPI).

Endpoint:
- GET  /                  dashboard HTML (static/index.html)
- GET  /health
- GET  /api/projects, /api/runs, /api/runs/{run_id}, /api/meetings,
       /api/tasks, /api/approvals, /api/usage, /api/audit
- POST /api/debate        {topic} -> buat run (logika sama seperti CLI)

Data dibaca dari folder runs/ dan SQLite bila ada (runs/mufakat.db dsb.);
bila tidak ada, kembalikan list kosong + status ok.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from mufakat.runner import (
        create_run,
        find_sqlite_db,
        list_runs,
        load_sqlite_table,
        read_run,
    )
except ImportError:  # pragma: no cover - bila paket belum terpasang
    from mufakat.runner import (  # type: ignore[no-redef]
        create_run,
        find_sqlite_db,
        list_runs,
        load_sqlite_table,
        read_run,
    )

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="MUFAKAT",
    description="Dashboard debat multi-AI menuju mufakat.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class DebateRequest(BaseModel):
    """Body POST /api/debate."""

    topic: str = Field(..., min_length=1, description="Topik debat.")
    provider: str = Field("mock", description="Provider debat (default: mock).")


def _db_items(table: str) -> list[dict]:
    """Item dari SQLite bila ada; else list kosong."""
    db_path = find_sqlite_db()
    if db_path is None:
        return []
    return load_sqlite_table(db_path, table)


def _api_list(items: list[dict]) -> dict:
    return {"status": "ok", "count": len(items), "items": items}


# ---------------------------------------------------------------------------
# Halaman & health
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Dashboard HTML."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict:
    """Health check."""
    db_path = find_sqlite_db()
    return {
        "status": "ok",
        "service": "mufakat-web",
        "runs_count": len(list_runs()),
        "sqlite": str(db_path) if db_path else None,
        "env": {"MUFAKAT_DB": bool(os.environ.get("MUFAKAT_DB"))},
    }


# ---------------------------------------------------------------------------
# API read
# ---------------------------------------------------------------------------
@app.get("/api/projects")
def api_projects() -> dict:
    """Daftar project (SQLite bila ada, else kosong)."""
    return _api_list(_db_items("projects"))


@app.get("/api/runs")
def api_runs() -> dict:
    """Daftar run dari folder runs/ (+ SQLite bila ada)."""
    items = list_runs()
    for row in _db_items("runs"):
        if not any(r["run_id"] == str(row.get("id", row.get("run_id", ""))) for r in items):
            items.append({"run_id": str(row.get("id", row.get("run_id", ""))), **row})
    return _api_list(items)


@app.get("/api/runs/{run_id}")
def api_run_detail(run_id: str) -> dict:
    """Detail satu run."""
    info = read_run(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Run tidak ditemukan: {run_id}")
    return {"status": "ok", **info}


@app.get("/api/meetings")
def api_meetings() -> dict:
    """Daftar meeting (SQLite bila ada, else kosong)."""
    return _api_list(_db_items("meetings"))


@app.get("/api/tasks")
def api_tasks() -> dict:
    """Daftar task (SQLite bila ada, else kosong)."""
    return _api_list(_db_items("tasks"))


@app.get("/api/approvals")
def api_approvals() -> dict:
    """Daftar approval (SQLite bila ada, else kosong)."""
    return _api_list(_db_items("approvals"))


@app.get("/api/usage")
def api_usage() -> dict:
    """Pemakaian & biaya (SQLite usage_ledger bila ada, else nol)."""
    ledger = _db_items("usage_ledger")
    total_cost = sum(float(row.get("cost_usd", 0) or 0) for row in ledger)
    providers: dict[str, dict] = {}
    for row in ledger:
        name = str(row.get("provider", "unknown"))
        entry = providers.setdefault(name, {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0})
        entry["tokens_in"] += int(row.get("tokens_in", 0) or 0)
        entry["tokens_out"] += int(row.get("tokens_out", 0) or 0)
        entry["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    return {
        "status": "ok",
        "total_cost_usd": total_cost,
        "providers": providers,
        "ledger_entries": len(ledger),
    }


@app.get("/api/audit")
def api_audit() -> dict:
    """Log audit (SQLite audit_logs bila ada, else dari file runs/)."""
    items = _db_items("audit_logs")
    if not items:
        for run in list_runs():
            items.append(
                {
                    "event": "run_completed",
                    "run_id": run["run_id"],
                    "status": run["status"],
                    "created_at": run.get("created_at", ""),
                }
            )
    return _api_list(items)


# ---------------------------------------------------------------------------
# API write
# ---------------------------------------------------------------------------
@app.post("/api/debate", status_code=201)
def api_debate(payload: DebateRequest) -> dict:
    """Buat run debat baru — logika sama seperti `mufakat run` di CLI."""
    result = create_run(payload.topic, provider=payload.provider, mode="debate")
    return {"status": "ok", **result}
