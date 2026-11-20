"""Server MCP MUFAKAT — SATU server FastMCP bernama ``mufakat``.

Transport: stdio (``mcp.run(transport="stdio")`` di :func:`main`).
Tool inti: debate_start, debate_status, pipeline_run, gate_report.
Tool domain (namespaced): core_list_agents, meeting_create, task_create,
project_create, git_status, filesystem_read, terminal_run, testing_run,
security_scan, research_search, evaluation_submit, approval_request,
observability_status.

Semua tool mengembalikan dict aman. Tidak ada tool yang mengeksekusi
perintah berbahaya: terminal_run hanya mengizinkan echo/ls/pytest,
filesystem_read menolak file rahasia, git_status read-only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from fastmcp import FastMCP

try:
    from mufakat.mcp_server.tools import (
        create_run_for_mcp,
        err,
        gate_report_for_run,
        git_status_safe,
        list_agents,
        new_id,
        ok,
        read_file_safe,
        run_terminal_command,
    )
    from mufakat.runner import list_runs, read_run, runs_dir, utcnow
except ImportError:  # bila dijalankan langsung sebagai script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from mufakat.mcp_server.tools import (  # type: ignore[no-redef]
        create_run_for_mcp,
        err,
        gate_report_for_run,
        git_status_safe,
        list_agents,
        new_id,
        ok,
        read_file_safe,
        run_terminal_command,
    )
    from mufakat.runner import list_runs, read_run, runs_dir, utcnow  # type: ignore[no-redef]

mcp = FastMCP("mufakat")


# ---------------------------------------------------------------------------
# Tool inti debat / pipeline / gate
# ---------------------------------------------------------------------------
@mcp.tool
def debate_start(topic: str) -> str:
    """Mulai debat baru tentang sebuah topik. Mengembalikan run_id."""
    result = create_run_for_mcp(topic, provider="mock", mode="debate")
    return str(result["run_id"])


@mcp.tool
def debate_status(run_id: str) -> dict:
    """Status satu run debat (baca runs/<run_id>/)."""
    info = read_run(run_id)
    if info is None:
        return err("Run tidak ditemukan.", run_id=run_id)
    info.pop("messages", None)
    return ok(**info)


@mcp.tool
def pipeline_run(spec_path: str = "", repo_path: str = "") -> dict:
    """Jalankan pipeline dari file spec dan/atau repo.

    Bila spec_path ada, isinya dipakai sebagai ide. Tanpa spec, pipeline
    berjalan dengan ide default dari repo_path.
    """
    idea = ""
    if spec_path:
        read = read_file_safe(spec_path)
        if not read.get("ok"):
            return err("Spec tidak bisa dibaca.", spec_path=spec_path, detail=read.get("error", ""))
        idea = str(read.get("content", ""))[:4000]
    if not idea:
        idea = f"Pipeline untuk repo: {repo_path or '.'}"
    result = create_run_for_mcp(idea, provider="mock", mode="pipeline")
    return ok(
        run_id=result["run_id"],
        status=result["status"],
        dir=result["dir"],
        spec_path=spec_path,
        repo_path=repo_path,
    )


@mcp.tool
def gate_report(run_id: str) -> dict:
    """Laporan gate satu run; belum terverifikasi bila tidak ada hasil gate."""
    return gate_report_for_run(run_id)


# ---------------------------------------------------------------------------
# Tool domain (namespaced)
# ---------------------------------------------------------------------------
@mcp.tool
def core_list_agents() -> dict:
    """Daftar agen yang terdaftar (mock bila registry belum terisi)."""
    return list_agents()


@mcp.tool
def meeting_create(topic: str, participants: str = "") -> dict:
    """Buat meeting (rapat konsensus) baru. Mengembalikan meeting_id."""
    meeting_id = new_id("meet")
    record = {
        "meeting_id": meeting_id,
        "topic": topic,
        "participants": [p.strip() for p in participants.split(",") if p.strip()],
        "status": "created",
        "created_at": utcnow(),
    }
    return ok(**record)


@mcp.tool
def task_create(title: str, project: str = "", assignee: str = "") -> dict:
    """Buat task baru di task board."""
    return ok(
        task_id=new_id("task"),
        title=title,
        project=project,
        assignee=assignee,
        status="todo",
        created_at=utcnow(),
    )


@mcp.tool
def project_create(name: str, description: str = "") -> dict:
    """Buat project baru."""
    return ok(
        project_id=new_id("proj"),
        name=name,
        description=description,
        status="active",
        created_at=utcnow(),
    )


@mcp.tool
def git_status(repo_path: str = ".") -> dict:
    """Status git read-only untuk sebuah repo lokal."""
    return git_status_safe(repo_path)


@mcp.tool
def filesystem_read(path: str) -> dict:
    """Baca file teks (menolak file rahasia, maks. 1 MB)."""
    return read_file_safe(path)


@mcp.tool
def terminal_run(command: str) -> dict:
    """Jalankan perintah terminal — HANYA echo, ls, pytest. Lainnya ditolak."""
    return run_terminal_command(command)


@mcp.tool
def testing_run(target: str = ".") -> dict:
    """Jalankan pytest --collect-only (aman, tanpa mengeksekusi test)."""
    if shutil.which("pytest") is None:
        return err("pytest tidak tersedia di lingkungan ini.", target=target)
    try:
        proc = subprocess.run(
            ["pytest", "-q", "--collect-only", target],
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return err("testing_run kehabisan waktu (timeout 120 detik).", target=target)
    except Exception as exc:  # noqa: BLE001
        return err(f"Gagal menjalankan pytest: {exc}", target=target)
    tail = (proc.stdout + proc.stderr)[-20000:]
    return ok(
        target=target,
        returncode=proc.returncode,
        summary=tail.strip().splitlines()[-5:] if tail.strip() else [],
        output=tail,
    )


@mcp.tool
def security_scan(target: str = ".") -> dict:
    """Status pemindai keamanan yang tersedia (tidak menjalankan scan otomatis)."""
    available = {
        name: shutil.which(name) is not None
        for name in ("semgrep", "bandit", "gitleaks", "trivy", "ruff")
    }
    return ok(
        target=target,
        scanners_available=available,
        status="pending",
        note=(
            "Scan tidak dijalankan otomatis dari tool ini; jalankan pemindai "
            "secara eksplisit (mis. `semgrep --config auto <target>`) dan "
            "simpan hasilnya di runs/<run_id>/gates/ agar gate_report terverifikasi."
        ),
    )


@mcp.tool
def research_search(query: str) -> dict:
    """Pencarian riset — belum terhubung ke sumber web; kembalikan status."""
    return ok(
        query=query,
        results=[],
        status="not_connected",
        note=(
            "research_search belum terhubung ke sumber web. "
            "Isi hasil pencarian dari sumber yang disetujui owner."
        ),
    )


@mcp.tool
def evaluation_submit(run_id: str, score: float, notes: str = "") -> dict:
    """Simpan evaluasi (skor 0–1) untuk satu run."""
    if not 0.0 <= score <= 1.0:
        return err("score harus di antara 0 dan 1.", run_id=run_id, score=score)
    info = read_run(run_id)
    if info is None:
        return err("Run tidak ditemukan.", run_id=run_id)
    record = {
        "run_id": run_id,
        "score": score,
        "notes": notes,
        "submitted_at": utcnow(),
    }
    path = runs_dir() / run_id / "evaluation.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return ok(**record, path=str(path))


@mcp.tool
def approval_request(title: str, run_id: str = "", requested_by: str = "") -> dict:
    """Minta persetujuan (approval) untuk sebuah keputusan/aksi."""
    return ok(
        approval_id=new_id("appr"),
        title=title,
        run_id=run_id,
        requested_by=requested_by,
        status="pending",
        created_at=utcnow(),
    )


@mcp.tool
def observability_status() -> dict:
    """Status observabilitas server: jumlah run, binary, env (ada/tidak)."""
    import os

    runs = list_runs()
    return ok(
        server="mufakat",
        transport="stdio",
        runs_count=len(runs),
        latest_run=runs[0]["run_id"] if runs else None,
        binaries={
            name: shutil.which(name) is not None
            for name in ("docker", "ruff", "pytest", "git")
        },
        api_keys_present={
            name: bool(os.environ.get(name))
            for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")
        },
        checked_at=utcnow(),
    )


def main() -> None:
    """Entry point console script ``mufakat-mcp``: jalankan server via stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
