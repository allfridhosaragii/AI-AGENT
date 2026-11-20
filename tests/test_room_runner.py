"""Test Local Runner dari suite utama (paket mufakat_runner di mufakat-room/runner).

Runner diuji lewat sys.path agar tetap bisa jalan tanpa instalasi terpisah.
Perintah host berbasis ``run_id`` (audit C2), bukan path bebas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mufakat-room" / "runner"))

import pytest  # noqa: E402
from mufakat_runner import host as host_mod  # noqa: E402
from mufakat_runner import worktree as worktree_mod  # noqa: E402


def _setup_host(tmp_path, monkeypatch):
    """Host + repo terdaftar (C2, N3): registrasi HANYA lewat registry
    (setara CLI lokal `mufakat-room-runner register`) — perintah
    native messaging `register_repo` sudah dihapus."""
    from mufakat_runner import registry as registry_mod

    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    assert registry_mod.register_repo("r", str(repo))["name"] == "r"
    host = host_mod.RunnerHost()
    assert host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "r1"}
    )["ok"] is True
    return host, repo


def test_runner_path_traversal_ditolak():
    for bad in ("../../etc/passwd", "/etc/passwd", ".."):
        with pytest.raises(ValueError):
            worktree_mod.validate_rel_path(bad)


def test_runner_commit_tanpa_token_ditolak(tmp_path, monkeypatch):
    host, _repo = _setup_host(tmp_path, monkeypatch)
    result = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x"}
    )
    assert result["ok"] is False


def test_runner_status_mode_manual():
    result = host_mod.handle_command({"command": "status"})
    assert result["ok"] is True
    assert result["mode"] == "manual_handoff"


def test_runner_path_bebas_ditolak(tmp_path, monkeypatch):
    """C2: perintah dengan path bebas (bukan run_id) ditolak."""
    host, _repo = _setup_host(tmp_path, monkeypatch)
    victim = tmp_path / "victim"
    victim.mkdir()
    assert host.handle_command(
        {"command": "apply_files", "worktree": str(victim), "files": []}
    )["ok"] is False
    assert host.handle_command(
        {"command": "cleanup", "worktree": str(victim)}
    )["ok"] is False
    assert victim.exists()
