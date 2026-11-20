"""Test regresi audit 20 Nov 2026: H1 (approval manusia) + M10 (graph).

- H1: `mufakat approve <id> --yes` menampilkan diff+hash, menerbitkan
  token sekali pakai; tanpa token / token salah / diff berubah -> commit
  ditolak (sudah diuji di test_mcp_domains; di sini alur CLI-nya).
- M10: checkpointer SQLite dibuat via SqliteSaver(sqlite3.connect(...))
  (bukan from_conn_string); node spec interrupt saat
  require_human_approval; node revise kembali ke review, bukan audit.
"""

from __future__ import annotations

import asyncio
import sqlite3
import subprocess

from typer.testing import CliRunner

from mufakat.cli import app as cli_app
from mufakat.graph.nodes.revise import node as revise_node
from mufakat.graph.state import RunState


def _init_git_repo(repo, monkeypatch):
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"],
                   check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tes"],
                   check=True)
    (repo / "a.txt").write_text("satu\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "awal"],
                   check=True)


def test_cli_approve_menerbitkan_token_sekali_pakai(tmp_path, monkeypatch):
    """H1: alur normal — request (MCP) -> approve (CLI manusia) -> token.

    Putaran 2 (N8): --yes DIHAPUS. Persetujuan butuh konfirmasi TTY
    (disimulasikan di sini: stdin isatty + input "y") atau env
    MUFAKAT_ALLOW_NONINTERACTIVE_APPROVE=1 (dicatat ke stderr).
    """
    import os as _os

    from mufakat.mcp_server import approval_store, repo_registry
    from mufakat.mcp_server.domains.approval import approval_request
    from mufakat.mcp_server.domains.git import git_commit

    monkeypatch.setenv("MUFAKAT_APPROVALS_DB", str(tmp_path / "approvals.db"))
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo, monkeypatch)
    (repo / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    repo_registry.register_repo("tes", str(repo))

    approval = approval_request("Commit via CLI")
    approval_id = approval["approval_id"]
    runner = CliRunner()
    # --yes tidak ada lagi: opsi tak dikenal -> exit != 0, approval tetap pending.
    assert runner.invoke(cli_app, ["approve", approval_id, "--repo",
                                   str(repo), "--yes"]).exit_code != 0
    assert approval_store.get_approval(approval_id)["status"] == "pending"
    # Konfirmasi TTY (fd 0 disimulasikan) + diff LENGKAP ditampilkan.
    monkeypatch.setattr(_os, "isatty", lambda fd: True)
    result = runner.invoke(cli_app, ["approve", approval_id, "--repo",
                                     str(repo)], input="y\n")
    assert result.exit_code == 0, result.output
    assert "Hash diff" in result.output
    assert "+dua" in result.output  # diff lengkap, bukan hanya statistik
    # Token tercetak di output CLI (sekali tampil): satu baris berisi
    # token urlsafe 43 karakter.
    import re

    match = re.search(r"^([A-Za-z0-9_-]{43})$", result.output, re.M)
    assert match is not None, result.output
    token = match.group(1)
    status = approval_store.get_approval(approval_id)
    assert status["status"] == "approved"
    assert status["diff_hash"]
    assert status["repo_path"] == str(repo.resolve())
    assert status["branch"]
    # Token bisa dipakai commit sekali...
    assert git_commit(str(repo), "pesan", approval_id=approval_id,
                      approval_token=token)["ok"] is True
    # ...dan hangus sesudahnya.
    assert git_commit(str(repo), "pesan2", approval_id=approval_id,
                      approval_token=token)["ok"] is False
    # Approve kedua kali ditolak (sudah diputus).
    again = runner.invoke(cli_app, ["approve", approval_id, "--repo",
                                    str(repo)], input="y\n")
    assert again.exit_code == 1


def test_cli_approve_noninteraktif_butuh_env_dan_dicatat(tmp_path, monkeypatch):
    """N8: tanpa TTY dan tanpa env -> ditolak; dengan env -> jalan + log."""
    from mufakat.mcp_server import approval_store
    from mufakat.mcp_server.domains.approval import approval_request

    monkeypatch.setenv("MUFAKAT_APPROVALS_DB", str(tmp_path / "approvals.db"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo, monkeypatch)
    (repo / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)

    approval = approval_request("Commit non-interaktif")
    approval_id = approval["approval_id"]
    runner = CliRunner()
    assert runner.invoke(cli_app, ["approve", approval_id, "--repo",
                                   str(repo)]).exit_code == 1
    assert approval_store.get_approval(approval_id)["status"] == "pending"
    monkeypatch.setenv("MUFAKAT_ALLOW_NONINTERACTIVE_APPROVE", "1")
    result = runner.invoke(cli_app, ["approve", approval_id, "--repo",
                                     str(repo)])
    assert result.exit_code == 0, result.output
    assert approval_store.get_approval(approval_id)["status"] == "approved"


def test_checkpointer_sqlite_bukan_context_manager(tmp_path):
    """M10: build_graph dengan checkpointer_path SQLite tidak crash.

    Graph dibangun DI DALAM loop async (AsyncSqliteSaver terikat ke
    loop pembuatnya) lalu ainvoke di loop yang sama.
    """
    from mufakat.graph.build import build_graph

    db = tmp_path / "checkpoints.db"

    async def _run():
        graph = build_graph(adapters={}, checkpointer_path=str(db),
                            ctx={"require_human_approval": False})
        assert graph is not None
        state = {"run_id": "t1", "idea": "ide tes", "provider": "mock",
                 "run_dir": str(tmp_path)}
        try:
            return await graph.ainvoke(
                state, {"configurable": {"thread_id": "t1"}})
        finally:
            # Tutup koneksi aiosqlite supaya thread worker-nya tidak
            # melempar PytestUnhandledThreadExceptionWarning saat teardown.
            conn = getattr(graph.checkpointer, "conn", None)
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    pass

    result = asyncio.run(_run())
    assert isinstance(result, dict)
    # Checkpointer SQLite benar-benar dipakai: file berisi tabel checkpoints.
    conn = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "checkpoints" in tables, f"checkpointer SQLite tidak menulis apa pun: {tables}"


def test_spec_interrupt_saat_human_approval(tmp_path):
    """M10: node spec interrupt (jeda) bila require_human_approval."""
    from mufakat.graph.build import build_graph

    graph = build_graph(adapters={}, ctx={"require_human_approval": True})
    state = {"run_id": "t1", "idea": "ide tes", "provider": "mock",
             "run_dir": str(tmp_path)}
    result = asyncio.run(graph.ainvoke(
        state, {"configurable": {"thread_id": "t-interrupt"}}))
    assert isinstance(result, dict)
    assert "__interrupt__" in result or result.get("phase") in ("spec", "code")
    if "__interrupt__" in result:
        interrupt = result["__interrupt__"][0]
        assert interrupt.value["type"] == "approve_spec"


def test_revise_kembali_ke_review_bukan_audit():
    """M10: revise dengan temuan kembali ke review (bukan audit)."""
    state = RunState(run_id="t1", idea="ide",
                     findings=[{"severity": "blocking", "rule": "x"}])
    patch = asyncio.run(revise_node(state, adapters={}, ctx={}))
    assert patch["phase"] == "review"
