"""Test 15 domain MCP MUFAKAT (ChatGPT §7).

Satu server FastMCP bernama ``mufakat`` tetap menjadi gateway;
tiap domain adalah modul terpisah di
``mufakat.mcp_server.domains`` dan mendaftarkan tool-nya sendiri.
"""

from __future__ import annotations

import asyncio

from mufakat.mcp_server.domains import DOMAINS, register_all, store
from mufakat.mcp_server.domains.approval import (
    approval_get_status,
    approval_request,
)
from mufakat.mcp_server.domains.git import git_commit
from mufakat.mcp_server.domains.meeting import (
    meeting_create,
    meeting_record_decision,
    meeting_submit_argument,
    meeting_submit_critique,
)
from mufakat.mcp_server.domains.memory import memory_list, memory_read, memory_write
from mufakat.mcp_server.domains.project import project_create, project_create_adr
from mufakat.mcp_server.domains.task import (
    task_assign,
    task_create,
    task_get_dependencies,
    task_update_status,
)
from mufakat.mcp_server.server import REGISTERED_TOOLS, list_tool_contracts, mcp


def test_lima_belas_domain_terdaftar():
    assert len(DOMAINS) == 15
    assert set(DOMAINS) == {
        "core", "communication", "meeting", "task", "memory", "project",
        "git", "filesystem", "terminal", "testing", "security", "research",
        "evaluation", "approval", "observability",
    }


def test_semua_tool_terdaftar_di_server():
    assert len(REGISTERED_TOOLS) >= 50
    # 17 nama lama dari test_smoke tetap ada.
    for expected in (
        "debate_start", "debate_status", "pipeline_run", "gate_report",
        "core_list_agents", "meeting_create", "task_create", "project_create",
        "git_status", "filesystem_read", "terminal_run", "testing_run",
        "security_scan", "research_search", "evaluation_submit",
        "approval_request", "observability_status",
    ):
        assert expected in REGISTERED_TOOLS, expected
    # Tool baru per domain juga terdaftar.
    for expected in (
        "agent_register", "agent_send_message", "meeting_submit_argument",
        "task_assign", "memory_write", "project_create_adr", "git_diff",
        "filesystem_propose_patch", "test_run_unit", "security_scan_secrets",
        "research_save_reference", "review_submit", "approval_get_status",
        "observability_list_runs",
    ):
        assert expected in REGISTERED_TOOLS, expected


def test_kontrak_tool_punya_permission():
    all_contracts = list_tool_contracts()
    assert len(all_contracts) == len(REGISTERED_TOOLS)
    permissions = {"read", "write-sandbox", "propose", "execute-approved",
                   "approval-required"}
    for contract in all_contracts:
        assert contract["domain"] in DOMAINS
        assert contract["permission"] in permissions, contract
        assert contract["description"]


def test_register_all_idempotent_pada_server_baru():
    from fastmcp import FastMCP

    fresh = FastMCP("test-fresh")
    names = register_all(fresh)
    assert len(names) == len(REGISTERED_TOOLS)
    assert set(names) == set(REGISTERED_TOOLS)


def test_list_tools_async():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert set(REGISTERED_TOOLS) <= names


def test_meeting_alur_lengkap():
    store.reset()
    created = meeting_create("Topik tes", participants="a,b")
    assert created["ok"] is True
    mid = created["meeting_id"]
    assert meeting_submit_argument(mid, "a", "Usulan A")["ok"] is True
    assert meeting_submit_critique(mid, "b", "Kritik B")["ok"] is True
    decision = meeting_record_decision(mid, "approve", dissent="minoritas: B")
    assert decision["ok"] is True
    assert decision["dissent"] == ["minoritas: B"]


def test_task_lifecycle_dan_dependency():
    store.reset()
    t1 = task_create("Task 1")
    t2 = task_create("Task 2", depends_on=t1["task_id"])
    assert task_assign(t2["task_id"], "coder")["assignee"] == "coder"
    assert task_update_status(t2["task_id"], "done")["status"] == "done"
    deps = task_get_dependencies(t2["task_id"])
    assert deps["depends_on"] == [t1["task_id"]]
    assert task_update_status(t2["task_id"], "salah")["ok"] is False


def test_memory_per_proyek():
    store.reset()
    assert memory_write("proj-1", "adr-1", "Pakai LangGraph")["ok"] is True
    assert memory_read("proj-1", "adr-1")["content"] == "Pakai LangGraph"
    assert memory_read("proj-2", "adr-1")["ok"] is False
    assert memory_list("proj-1")["count"] == 1


def test_project_adr():
    store.reset()
    project = project_create("Proyek tes")
    adr = project_create_adr(project["project_id"], "ADR-1", "Pakai SQLite")
    assert adr["ok"] is True
    assert adr["title"] == "ADR-1"


def test_approval_record_decision_tidak_terdaftar_di_mcp():
    """H1: AI tidak boleh memutuskan approval lewat MCP."""
    assert "approval_record_decision" not in REGISTERED_TOOLS
    from mufakat.mcp_server.domains.approval import CONTRACTS

    assert {c["name"] for c in CONTRACTS} == {
        "approval_request", "approval_get_status"}


def test_git_commit_butuh_approval_manusia(tmp_path, monkeypatch):
    """H1: commit butuh approval manusia (SQLite) + token sekali pakai
    yang terikat hash diff; diff berubah -> ditolak; token hangus
    setelah dipakai."""
    import subprocess

    from mufakat.mcp_server import approval_store, repo_registry
    from mufakat.mcp_server.domains.approval import decide_approval

    monkeypatch.setenv("MUFAKAT_APPROVALS_DB", str(tmp_path / "approvals.db"))
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"],
                   check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tes"],
                   check=True)
    (repo / "a.txt").write_text("satu\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "awal"],
                   check=True)
    (repo / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    # GPT 5: operasi Git MCP hanya untuk repo terdaftar.
    repo_registry.register_repo("tes", str(repo))

    store.reset()
    # Tanpa approval/token: ditolak.
    assert git_commit(str(repo), "pesan", approval_id="tidak-ada")["ok"] is False
    approval = approval_request("Commit tes")
    assert approval["ok"] is True
    assert git_commit(str(repo), "pesan",
                      approval_id=approval["approval_id"])["ok"] is False
    # Approval yang DITOLAK manusia juga tidak cukup.
    rejected = approval_request("Commit tes ditolak")
    decide_approval(rejected["approval_id"], False, decided_by="human-cli")
    assert git_commit(str(repo), "pesan",
                      approval_id=rejected["approval_id"],
                      approval_token="apa-pun")["ok"] is False
    # Disetujui manusia (CLI) -> token sekali pakai terikat hash diff.
    diff_hash = approval_store.diff_hash_for_repo(str(repo))
    decided = decide_approval(approval["approval_id"], True,
                              decided_by="human-cli", diff_hash=diff_hash)
    token = decided["approval_token"]
    assert approval_get_status(approval["approval_id"])["status"] == "approved"
    # Diff berubah setelah disetujui -> ditolak.
    (repo / "a.txt").write_text("satu\ndua\ntiga\n", encoding="utf-8")
    assert git_commit(str(repo), "pesan",
                      approval_id=approval["approval_id"],
                      approval_token=token)["ok"] is False
    (repo / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    ok_result = git_commit(str(repo), "pesan",
                           approval_id=approval["approval_id"],
                           approval_token=token)
    assert ok_result["ok"] is True
    # Token sekali pakai: pemakaian kedua ditolak.
    (repo / "b.txt").write_text("baru\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert git_commit(str(repo), "pesan2",
                      approval_id=approval["approval_id"],
                      approval_token=token)["ok"] is False


def test_filesystem_propose_patch_tidak_menulis(tmp_path, monkeypatch):
    from mufakat.mcp_server.domains.filesystem import filesystem_propose_patch

    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    target = tmp_path / "a.txt"
    target.write_text("lama\n", encoding="utf-8")
    result = filesystem_propose_patch(str(target), "baru\n", reason="tes")
    assert result["ok"] is True
    assert result["status"] == "proposed"
    assert target.read_text(encoding="utf-8") == "lama\n"
    assert filesystem_propose_patch(str(tmp_path / ".env"),
                                    "x")["ok"] is False
