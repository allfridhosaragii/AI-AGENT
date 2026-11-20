"""Test Local Runner dari suite utama (paket mufakat_runner di mufakat-room/runner).

Runner diuji lewat sys.path agar tetap bisa jalan tanpa instalasi terpisah.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mufakat-room" / "runner"))

import pytest  # noqa: E402
from mufakat_runner import host as host_mod  # noqa: E402
from mufakat_runner import worktree as worktree_mod  # noqa: E402


def test_runner_path_traversal_ditolak():
    for bad in ("../../etc/passwd", "/etc/passwd", ".."):
        with pytest.raises(ValueError):
            worktree_mod.validate_rel_path(bad)


def test_runner_commit_tanpa_token_ditolak(tmp_path):
    result = host_mod.handle_command(
        {"command": "commit", "worktree": str(tmp_path), "message": "x"}
    )
    assert result["ok"] is False


def test_runner_status_mode_manual():
    result = host_mod.handle_command({"command": "status"})
    assert result["ok"] is True
    assert result["mode"] == "manual_handoff"
