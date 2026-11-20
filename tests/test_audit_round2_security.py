"""Test regresi audit putaran 2 (20 Nov 2026) — bagian keamanan MCP /
approval / runner Python (pekerja 2).

- C3-sisa: root workspace eksplisit (MUFAKAT_WORKSPACE_ROOTS wajib),
  HOME/leluhur HOME ditolak, blocklist diperluas.
- GPT 1: `allowed_roots` dihapus dari parameter MCP filesystem_read /
  filesystem_propose_patch.
- GPT 5: authorization layer ditegakkan SEBELUM tool MCP jalan;
  operasi Git hanya untuk repo terdaftar.
- N12 + GPT 3: hash kosong ditolak; verify+consume atomik;
  decide_approval atomik; approval terikat repo/branch/worktree.
- N8: `--yes` dihapus dari `mufakat approve`; CLI tampilkan diff
  lengkap; agen CLI ditolak di cwd repo utama (DB approval).
- L4: adapter CLI meneruskan prompt dengan `--`.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# C3-sisa
# ---------------------------------------------------------------------------
def test_c3_sisa_root_home_ditolak(tmp_path, monkeypatch):
    """C3-sisa (PoC): server jalan dengan cwd=HOME tidak boleh membaca
    kredensial — root HOME / leluhur HOME ditolak mentah-mentah."""
    from mufakat.mcp_server.tools import read_file_safe, workspace_roots

    home = Path.home()
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(home))
    assert workspace_roots() == []
    assert read_file_safe(str(home / ".bashrc"))["ok"] is False
    # Leluhur HOME (/) juga ditolak.
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", "/")
    assert workspace_roots() == []
    # Tanpa env sama sekali: fail-closed.
    monkeypatch.delenv("MUFAKAT_WORKSPACE_ROOTS")
    assert workspace_roots() == []
    assert read_file_safe(str(tmp_path / "x.txt"))["ok"] is False


def test_c3_sisa_blocklist_diperluas_ditolak(tmp_path, monkeypatch):
    """C3-sisa (PoC audit): .npmrc, .docker/config.json, .bash_history,
    .gnupg, .kube/config, .pypirc, .mufakat/runner.json,
    runs/approvals.db, *.db, *.sqlite3, Cookies, Login Data ditolak
    walau berada di dalam root workspace."""
    from mufakat.mcp_server.tools import read_file_safe

    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    blocked = [
        tmp_path / ".npmrc",
        tmp_path / ".docker" / "config.json",
        tmp_path / ".bash_history",
        tmp_path / ".zsh_history",
        tmp_path / ".gnupg" / "private-keys-v1.d" / "key",
        tmp_path / ".kube" / "config",
        tmp_path / ".pypirc",
        tmp_path / ".mufakat" / "runner.json",
        tmp_path / "runs" / "approvals.db",
        tmp_path / "data.db",
        tmp_path / "data.sqlite3",
        tmp_path / "Cookies",
        tmp_path / "Login Data",
        tmp_path / ".mozilla" / "profiles.ini",
        tmp_path / ".local" / "share" / "x",
        tmp_path / "AppData" / "x",
    ]
    for target in blocked:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("rahasia", encoding="utf-8")
        assert read_file_safe(str(target))["ok"] is False, target
    allowed = tmp_path / "biasa.txt"
    allowed.write_text("halo", encoding="utf-8")
    assert read_file_safe(str(allowed))["ok"] is True


def test_c3_sisa_env_wajib_bukan_cwd(tmp_path, monkeypatch):
    """C3-sisa: cwd BUKAN lagi root implisit — file di cwd tanpa env
    ditolak, dengan env yang menunjuk cwd diizinkan."""
    from mufakat.mcp_server.tools import read_file_safe

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "a.txt"
    target.write_text("ok", encoding="utf-8")
    monkeypatch.delenv("MUFAKAT_WORKSPACE_ROOTS", raising=False)
    assert read_file_safe(str(target))["ok"] is False
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    assert read_file_safe(str(target))["ok"] is True


# ---------------------------------------------------------------------------
# GPT 1
# ---------------------------------------------------------------------------
def test_gpt1_allowed_roots_dihapus_dari_parameter_mcp():
    """GPT 1: filesystem_read / filesystem_propose_patch TIDAK PUNYA
    parameter allowed_roots — pemanggil AI tidak bisa memanggil
    filesystem_read(path=..., allowed_roots=["/"])."""
    from mufakat.mcp_server.domains.filesystem import (
        filesystem_propose_patch,
        filesystem_read,
    )

    assert "allowed_roots" not in inspect.signature(filesystem_read).parameters
    assert "allowed_roots" not in inspect.signature(
        filesystem_propose_patch).parameters
    with pytest.raises(TypeError):
        filesystem_read("/some/private/file", allowed_roots=["/"])
    with pytest.raises(TypeError):
        filesystem_propose_patch("/some/private/file", "x",
                                 allowed_roots=["/"])


# ---------------------------------------------------------------------------
# GPT 5 — authorization layer + registry repo
# ---------------------------------------------------------------------------
def _fresh_mcp():
    from fastmcp import FastMCP

    from mufakat.mcp_server.domains import register_all

    mcp = FastMCP("mufakat-test")
    register_all(mcp)
    return mcp


async def _call(mcp, name, args):
    result = await mcp.call_tool(name, args)
    return result.structured_content or {}


def test_gpt5_git_tanpa_registry_ditolak_mcp(tmp_path, monkeypatch):
    """GPT 5: operasi Git MCP menolak repo yang tidak terdaftar —
    SEBELUM tool jalan (authorization layer)."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    mcp = _fresh_mcp()
    repo = tmp_path / "repo"
    repo.mkdir()
    for tool in ("git_status", "git_diff", "git_branch"):
        res = asyncio.run(_call(mcp, tool, {"repo_path": str(repo)}))
        assert res.get("ok") is False, (tool, res)
        assert "terdaftar" in str(res.get("error", "")), res


def test_gpt5_git_repo_terdaftar_diterima(tmp_path, monkeypatch):
    """GPT 5: repo terdaftar lewat registry bisa dipakai git_status."""
    from mufakat.mcp_server import repo_registry

    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    repo_registry.register_repo("r", str(repo))
    mcp = _fresh_mcp()
    res = asyncio.run(_call(mcp, "git_status", {"repo_path": str(repo)}))
    assert res.get("ok") is True, res


def test_gpt5_register_repo_home_ditolak(tmp_path, monkeypatch):
    """N3: HOME tidak bisa didaftarkan sebagai repo."""
    from mufakat.mcp_server import repo_registry

    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    with pytest.raises(ValueError):
        repo_registry.register_repo("home", str(Path.home()))
    with pytest.raises(ValueError):
        repo_registry.register_repo("root", "/")


def test_gpt5_approval_required_tanpa_token_ditolak_dulu(tmp_path, monkeypatch):
    """GPT 5: git_commit tanpa approval_id/token ditolak authorization
    layer sebelum tool jalan."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    mcp = _fresh_mcp()
    res = asyncio.run(_call(mcp, "git_commit", {
        "repo_path": str(tmp_path), "message": "x"}))
    assert res.get("ok") is False, res
    assert res.get("authorized") is False


def test_gpt5_terminal_run_ditolak_layer(tmp_path, monkeypatch):
    """GPT 5: terminal_run dengan perintah di luar allowlist ditolak
    authorization layer (bukan hanya di dalam tool)."""
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    mcp = _fresh_mcp()
    res = asyncio.run(_call(mcp, "terminal_run", {"command": "rm -rf /"}))
    assert res.get("ok") is False, res
    assert res.get("authorized") is False
    res = asyncio.run(_call(mcp, "terminal_run", {"command": "echo halo"}))
    assert res.get("ok") is True, res


def test_gpt5_execute_approved_target_di_luar_workspace_ditolak(
        tmp_path, monkeypatch):
    """GPT 5: testing_run / security_scan_secrets dengan target di luar
    workspace ditolak sebelum eksekusi."""
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    mcp = _fresh_mcp()
    res = asyncio.run(_call(mcp, "testing_run", {"target": "/etc"}))
    assert res.get("ok") is False, res
    assert res.get("authorized") is False


def test_gpt5_tool_tidak_dikenal_ditolak():
    """GPT 5: fail-closed — tool tanpa kontrak ditolak."""
    from mufakat.mcp_server.authorization import check_permission

    assert check_permission("tool_tidak_ada", None, {}) is not None


# ---------------------------------------------------------------------------
# N12 + GPT 3 — approval store
# ---------------------------------------------------------------------------
def _approved(tmp_path, monkeypatch, repo=None, branch="main"):
    """Approval yang disetujui dengan ikatan hash/repo/branch."""
    from mufakat.mcp_server import approval_store
    from mufakat.mcp_server.domains.approval import decide_approval

    monkeypatch.setenv("MUFAKAT_APPROVALS_DB", str(tmp_path / "approvals.db"))
    approval_store.create_approval(
        "appr-tes", "tes", diff_hash="abc123")
    decided, token = approval_store.decide_approval(
        "appr-tes", True, decided_by="human-cli", diff_hash="abc123",
        repo_path=str(repo) if repo else "",
        branch=branch if repo else "")
    assert decided is not None and token
    return approval_store, token, decide_approval


def test_n12_hash_kosong_ditolak(tmp_path, monkeypatch):
    """N12: verify_token dengan hash saat ini kosong DITOLAK (dulu
    cek dilewati bila `if current_diff_hash and ...`)."""
    store, token, _ = _approved(tmp_path, monkeypatch)
    valid, reason = store.verify_token("appr-tes", token,
                                       current_diff_hash="")
    assert valid is False
    assert "kosong" in reason
    valid, _ = store.verify_and_consume_token("appr-tes", token,
                                              current_diff_hash="")
    assert valid is False
    # Token belum hangus karena verifikasi gagal.
    assert store.get_approval("appr-tes")["used"] is False


def test_gpt3_verify_consume_atomik_token_hanya_sekali(tmp_path, monkeypatch):
    """GPT 3: verify+consume atomik — pemakaian kedua token ditolak."""
    store, token, _ = _approved(tmp_path, monkeypatch)
    valid, _ = store.verify_and_consume_token("appr-tes", token,
                                              current_diff_hash="abc123")
    assert valid is True
    valid, reason = store.verify_and_consume_token("appr-tes", token,
                                                   current_diff_hash="abc123")
    assert valid is False
    assert "dipakai" in reason


def test_gpt3_approval_terikat_repo_dan_branch(tmp_path, monkeypatch):
    """GPT 3: approval terikat repo + branch — commit dari repo/branch
    lain ditolak."""
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    store, token, _ = _approved(tmp_path, monkeypatch, repo=repo_a,
                                branch="main")
    valid, _ = store.verify_token("appr-tes", token,
                                  current_diff_hash="abc123",
                                  repo_path=str(repo_a), branch="main")
    assert valid is True
    valid, reason = store.verify_token("appr-tes", token,
                                       current_diff_hash="abc123",
                                       repo_path=str(repo_b), branch="main")
    assert valid is False
    assert "Repo" in reason
    valid, reason = store.verify_token("appr-tes", token,
                                       current_diff_hash="abc123",
                                       repo_path=str(repo_a), branch="lain")
    assert valid is False
    assert "Branch" in reason


def test_gpt3_decide_approval_hanya_sekali(tmp_path, monkeypatch):
    """GPT 3: decide_approval atomik — keputusan kedua tidak
    menghasilkan token baru."""
    from mufakat.mcp_server import approval_store

    monkeypatch.setenv("MUFAKAT_APPROVALS_DB", str(tmp_path / "approvals.db"))
    approval_store.create_approval("appr-x", "tes", diff_hash="h1")
    record, token = approval_store.decide_approval(
        "appr-x", True, decided_by="human-cli", diff_hash="h1")
    assert record is not None and token
    record2, token2 = approval_store.decide_approval(
        "appr-x", False, decided_by="human-cli", diff_hash="h1")
    assert token2 is None
    assert record2["status"] == "approved"


# ---------------------------------------------------------------------------
# N8 — agen CLI di worktree/sandbox
# ---------------------------------------------------------------------------
def test_n8_run_cli_tolak_cwd_repo_utama(tmp_path):
    """N8: agen CLI ditolak bila cwd berisi DB approval utama."""
    from mufakat.adapters._cli import run_cli
    from mufakat.adapters.base import AdapterError

    main_repo = tmp_path / "repo"
    (main_repo / "runs").mkdir(parents=True)
    (main_repo / "runs" / "approvals.db").write_bytes(b"SQLite")
    with pytest.raises(AdapterError):
        asyncio.run(run_cli("test", "test", ["echo", "hi"],
                            {"cwd": str(main_repo)}))
    # Worktree tanpa DB approval: jalan.
    wt = tmp_path / "wt"
    wt.mkdir()
    reply = asyncio.run(run_cli("test", "test", ["echo", "hi"],
                                {"cwd": str(wt)}))
    assert reply.text == "hi"


def test_n8_run_cli_tolak_cwd_home():
    """N8: agen CLI ditolak bila cwd adalah HOME."""
    from mufakat.adapters._cli import run_cli
    from mufakat.adapters.base import AdapterError

    with pytest.raises(AdapterError):
        asyncio.run(run_cli("test", "test", ["echo", "hi"],
                            {"cwd": str(Path.home())}))


def test_n8_run_cli_pakai_worktree_dari_ctx(tmp_path):
    """N8: ctx worktree dipakai sebagai cwd (pipeline mengisi ctx
    dengan worktree run)."""
    from mufakat.adapters._cli import run_cli

    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "marker.txt").write_text("x", encoding="utf-8")
    reply = asyncio.run(run_cli("test", "test", ["ls", "marker.txt"],
                                {"worktree": str(wt)}))
    assert "marker.txt" in reply.text


# ---------------------------------------------------------------------------
# L4 — prompt dengan --
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("module_name,adapter_cls", [
    ("mufakat.adapters.cli_codex", "CodexAdapter"),
    ("mufakat.adapters.cli_claude", "ClaudeAdapter"),
    ("mufakat.adapters.cli_copilot", "CopilotAdapter"),
    ("mufakat.adapters.cli_opencode", "OpenCodeAdapter"),
    ("mufakat.adapters.cli_antigravity", "AntigravityAdapter"),
])
def test_l4_adapter_teruskan_prompt_dengan_dashdash(module_name, adapter_cls,
                                                    monkeypatch):
    """L4: prompt (termasuk yang diawali `-`) diteruskan setelah `--`
    sehingga tidak dibaca sebagai opsi CLI."""
    import importlib

    module = importlib.import_module(module_name)
    adapter = getattr(module, adapter_cls)()
    captured: dict = {}

    async def _fake_run_cli(name, family, cmd, ctx):
        from mufakat.adapters.base import Reply

        captured["cmd"] = cmd
        return Reply(text="ok", provider=name, family=family, raw="")

    monkeypatch.setattr(module, "run_cli", _fake_run_cli)
    asyncio.run(adapter.ask("--help --evil", ctx={}))
    cmd = captured["cmd"]
    assert "--" in cmd, cmd
    dashdash = cmd.index("--")
    prompt = cmd[dashdash + 1]
    assert prompt == "--help --evil", cmd
    assert cmd[dashdash + 1:] == ["--help --evil"]
