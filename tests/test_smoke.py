"""Smoke test MUFAKAT: CLI (T12-T14), MCP (T13), Web (T15).

Paket diimpor dari instalasi editable (`pip install -e .`); layout
kanonik adalah `src/mufakat/` dan tidak ada lagi tree flat di root.
"""

from __future__ import annotations

import json
import os

from typer.testing import CliRunner

from mufakat.cli import app as cli_app
from mufakat.mcp_server import server as mcp_server
from mufakat.mcp_server.server import (
    debate_start,
    debate_status,
    filesystem_read,
    gate_report,
    mcp,
    terminal_run,
)
from mufakat.runner import create_run, read_run
from mufakat.web.app import app as web_app


# ---------------------------------------------------------------------------
# Runner / CLI
# ---------------------------------------------------------------------------
def test_create_run_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = create_run("Buat REST API todo dengan FastAPI + test + audit", output="runs")
    run_dir = tmp_path / "runs" / result["run_id"]
    assert (run_dir / "transcript.jsonl").is_file()
    assert (run_dir / "rounds" / "round-01.md").is_file()
    assert (run_dir / "spec.md").is_file()
    assert (run_dir / "final_report.md").is_file()
    lines = [json.loads(x) for x in
             (run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
             if x.strip()]
    assert len(lines) >= 1
    required = (
        "run_id", "round", "phase", "agent_id", "role",
        "model_family", "content", "timestamp",
    )
    for line in lines:
        for field in required:
            assert field in line
    info = read_run(result["run_id"])
    assert info is not None and info["message_count"] == len(lines)


def test_cli_help_and_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    help_cmds = [
        ["--help"],
        ["run", "--help"],
        ["debate", "--help"],
        ["resume", "--help"],
        ["status", "--help"],
        ["doctor", "--help"],
    ]
    for args in help_cmds:
        res = runner.invoke(cli_app, args)
        assert res.exit_code == 0, (args, res.output)
    res = runner.invoke(cli_app, ["run", "Ide tes", "--output", "runs"])
    assert res.exit_code == 0, res.output
    res = runner.invoke(cli_app, ["doctor"])
    assert res.exit_code == 0
    assert "OPENAI_API_KEY" in res.output
    # Nilai key tidak boleh bocor ke output doctor.
    os.environ["OPENAI_API_KEY"] = "sk-RAHASIA-YANG-TIDAK-BOLEH-MUNCUL"
    try:
        res = runner.invoke(cli_app, ["doctor"])
        assert "sk-RAHASIA-YANG-TIDAK-BOLEH-MUNCUL" not in res.output
    finally:
        del os.environ["OPENAI_API_KEY"]


def test_cli_status_missing_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli_app, ["status", "tidakada"])
    assert res.exit_code == 1


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------
def test_mcp_tools_registered():
    names = set()
    manager = getattr(mcp, "_tool_manager", None)
    if manager is not None:
        try:
            names = set(getattr(manager, "_tools", {}).keys())
        except Exception:
            names = set()
    if not names:  # fallback: nama fungsi di modul server
        names = {n for n in dir(mcp_server) if not n.startswith("_")}
    for expected in (
        "debate_start",
        "debate_status",
        "pipeline_run",
        "gate_report",
        "core_list_agents",
        "meeting_create",
        "task_create",
        "project_create",
        "git_status",
        "filesystem_read",
        "terminal_run",
        "testing_run",
        "security_scan",
        "research_search",
        "evaluation_submit",
        "approval_request",
        "observability_status",
    ):
        assert expected in names, expected


def test_mcp_terminal_allowlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ok = terminal_run("echo halo")
    assert ok["ok"] is True and "halo" in ok["stdout"]
    denied = terminal_run("rm -rf /")
    assert denied["ok"] is False
    denied2 = terminal_run("ls; rm -rf /")
    assert denied2["ok"] is False


def test_mcp_filesystem_refuses_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-rahasia", encoding="utf-8")
    assert filesystem_read(str(tmp_path / ".env"))["ok"] is False
    (tmp_path / "biasa.txt").write_text("halo", encoding="utf-8")
    got = filesystem_read(str(tmp_path / "biasa.txt"))
    assert got["ok"] is True and got["content"] == "halo"


def test_mcp_debate_start_and_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = debate_start("Topik tes")
    assert isinstance(run_id, str) and len(run_id) == 8
    status = debate_status(run_id)
    assert status["ok"] is True and status["run_id"] == run_id
    gate = gate_report(run_id)
    assert gate["verified"] is False and gate["status"] == "belum terverifikasi"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------
def test_web_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.chdir(tmp_path)
    create_run("Topik web", output="runs")
    client = TestClient(web_app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200
    assert "MUFAKAT" in client.get("/").text
    for path in (
        "/api/projects",
        "/api/runs",
        "/api/meetings",
        "/api/tasks",
        "/api/approvals",
        "/api/usage",
        "/api/audit",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.json()["status"] == "ok"
    assert client.get("/api/runs").json()["count"] == 1
    res = client.post("/api/debate", json={"topic": "Debat via web"})
    assert res.status_code == 201
    run_id = res.json()["run_id"]
    assert client.get(f"/api/runs/{run_id}").status_code == 200
    assert client.get("/api/runs/tidakada").status_code == 404
