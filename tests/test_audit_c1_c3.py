"""Test regresi audit 20 Nov 2026: C3, M1, M12, ChatGPT I + web auth.

- C3: filesystem_read hanya di dalam allowlist workspace; symlink
  ditolak; ~/.codex/auth.json, ~/.ssh/id_ed25519, ~/.config/gh/hosts.yml
  dan *.sqlite ditolak (PoC audit).
- M1: SHELL_META berisi newline/CR asli — `ls runs` dan
  `pytest tests/test_main.py` tidak lagi ditolak karena huruf n/r.
- M12: run_id=".." ditolak di semua pintu masuk (web & MCP).
- ChatGPT I: nama provider config == adapter (openrouter, gemini);
  meta_api berstatus needs_policy_review (bukan klaim Muse Spark).
- Web: local-only tanpa token; bila MUFAKAT_WEB_TOKEN diset, POST
  /api/debate wajib header X-MUFAKAT-TOKEN.
"""

from __future__ import annotations

from pathlib import Path

from mufakat.mcp_server.tools import SHELL_META, read_file_safe, run_terminal_command
from mufakat.runner import read_run


def test_shell_meta_berisi_newline_asli_bukan_huruf(tmp_path, monkeypatch):
    """M1: SHELL_META berisi '\\n' dan '\\r' asli, bukan huruf n/r/'\\'."""
    assert "\n" in SHELL_META
    assert "\r" in SHELL_META
    assert "n" not in SHELL_META
    assert "r" not in SHELL_META
    assert "\\" not in SHELL_META
    monkeypatch.chdir(tmp_path)
    assert run_terminal_command("ls runs")["ok"] is True
    # Perintah pytest ditolak karena tidak di allowlist (C1), BUKAN
    # karena metakarakter — pesannya harus menyebut allowlist.
    denied = run_terminal_command("pytest tests/test_main.py")
    assert denied["ok"] is False
    assert "pytest" in denied["error"].lower() or "allowlist" in denied["error"].lower()
    # Metakarakter asli tetap ditolak.
    assert run_terminal_command("ls; echo x")["ok"] is False
    assert run_terminal_command("echo halo\ndunia")["ok"] is False


def test_filesystem_read_hanya_allowlist_workspace(tmp_path, monkeypatch):
    """C3: file di luar workspace ditolak walau namanya tidak sensitif."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    (tmp_path / "boleh.txt").write_text("ok", encoding="utf-8")
    assert read_file_safe(str(tmp_path / "boleh.txt"))["ok"] is True
    outside = tmp_path.parent / "di-luar.txt"
    outside.write_text("rahasia", encoding="utf-8")
    try:
        assert read_file_safe(str(outside))["ok"] is False
    finally:
        outside.unlink(missing_ok=True)


def test_filesystem_read_kredensial_cli_ditolak(tmp_path, monkeypatch):
    """C3 (PoC audit): token Codex/GitHub CLI & kunci SSH ditolak."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    home = Path.home()
    for target in (home / ".codex" / "auth.json",
                   home / ".ssh" / "id_ed25519",
                   home / ".config" / "gh" / "hosts.yml",
                   home / ".claude" / "settings.json",
                   home / ".aws" / "credentials",
                   home / ".git-credentials"):
        assert read_file_safe(str(target))["ok"] is False, target
    # *.sqlite juga diblokir, bahkan di dalam workspace.
    db = tmp_path / "data.sqlite"
    db.write_bytes(b"SQLite format 3\x00")
    assert read_file_safe(str(db))["ok"] is False


def test_filesystem_read_symlink_ditolak(tmp_path, monkeypatch):
    """C3: symlink (file maupun folder) tidak boleh dibaca."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MUFAKAT_WORKSPACE_ROOTS", str(tmp_path))
    outside = tmp_path.parent / "target-rahasia.txt"
    outside.write_text("rahasia", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
        assert read_file_safe(str(link))["ok"] is False
        link_dir = tmp_path / "linkdir"
        link_dir.symlink_to(tmp_path.parent, target_is_directory=True)
        assert read_file_safe(str(link_dir / "target-rahasia.txt"))["ok"] is False
    finally:
        outside.unlink(missing_ok=True)


def test_run_id_traversal_ditolak_semua_pintu(tmp_path, monkeypatch):
    """M12: run_id='..' ditolak di runner, MCP gate_report, dan web."""
    monkeypatch.chdir(tmp_path)
    assert read_run("..") is None
    assert read_run("../evil") is None
    assert read_run("") is None
    from mufakat.mcp_server.tools import gate_report_for_run

    assert gate_report_for_run("..")["ok"] is False
    assert gate_report_for_run("a/b")["ok"] is False
    from fastapi.testclient import TestClient

    from mufakat.web.app import app

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/runs/..").status_code in (400, 404)
    assert client.get("/api/runs/%2E%2E").status_code in (400, 404)


def test_nama_provider_config_sama_dengan_adapter():
    """ChatGPT I: config memakai 'openrouter' & 'gemini' (bukan
    openrouter_free/gemini_api) dan runner memakainya."""
    import yaml

    config_path = Path(__file__).resolve().parent.parent / "config" / "providers.yaml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "openrouter" in data["adapters"]
    assert "gemini" in data["adapters"]
    assert "openrouter_free" not in data["adapters"]
    assert "gemini_api" not in data["adapters"]
    from mufakat.provider_registry import default_registry

    registry = default_registry()
    assert registry.get("openrouter") is not None
    assert registry.get("gemini") is not None
    assert registry.get("openrouter_free") is None
    assert registry.get("gemini_api") is None


def test_meta_api_needs_policy_review_bukan_muse_spark():
    """ChatGPT I: meta_api/llama-4-maverick TIDAK diklaim sebagai Muse Spark."""
    from mufakat.provider_registry import default_registry

    meta = default_registry().get("meta_api")
    assert meta is not None
    assert meta.status == "needs_policy_review"


def test_web_local_only_tanpa_token_dan_auth_bila_token_diset(
        tmp_path, monkeypatch):
    """Web: local-only bila MUFAKAT_WEB_TOKEN kosong; bila diset, POST
    /api/debate tanpa token yang benar -> 401."""

    from fastapi.testclient import TestClient

    from mufakat.web.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MUFAKAT_WEB_TOKEN", raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/health").json()["local_only"] is True
    assert client.get("/health").json()["auth_required"] is False

    monkeypatch.setenv("MUFAKAT_WEB_TOKEN", "token-rahasia-uji")
    assert client.get("/health").json()["local_only"] is False
    assert client.get("/health").json()["auth_required"] is True
    res = client.post("/api/debate", json={"topic": "tes", "provider": "mock"})
    assert res.status_code == 401
    res = client.post("/api/debate", json={"topic": "tes", "provider": "mock"},
                      headers={"X-MUFAKAT-TOKEN": "salah"})
    assert res.status_code == 401
