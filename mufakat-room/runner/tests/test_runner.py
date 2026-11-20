"""Test Local Runner MUFAKAT Room (Claude §T11–T12).

- Path traversal ditolak (``../../etc/passwd``).
- Native messaging encode/decode roundtrip.
- Commit tanpa approval token ditolak; dengan token valid jalan sekali.
- Sandbox tanpa Docker dilaporkan belum terverifikasi (bukan pura-pura jalan).
- Verdict: ESKALASI bila anti-loop memicu.
"""


import importlib.util
from pathlib import Path as _Path

import pytest

from mufakat_runner import host as host_mod
from mufakat_runner import sandbox as sandbox_mod
from mufakat_runner import verdict as verdict_mod
from mufakat_runner import worktree as worktree_mod

_install_host_path = _Path(__file__).resolve().parent.parent / "install_host.py"
_spec = importlib.util.spec_from_file_location("mufakat_room_install_host", _install_host_path)
_install_host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_install_host)
host_manifest = _install_host.host_manifest


def test_path_traversal_ditolak():
    for bad in ("../../etc/passwd", "../secret.txt", "/etc/passwd", "..\\..\\win.ini", ""):
        with pytest.raises(ValueError):
            worktree_mod.validate_rel_path(bad)


def test_path_rel_valid():
    assert str(worktree_mod.validate_rel_path("src/app.py")) == "src/app.py"
    assert str(worktree_mod.validate_rel_path("a/b/c.txt")) == "a/b/c.txt"


def test_apply_files_replace_dan_patch(tmp_path):
    worktree_mod.apply_files(
        tmp_path, [{"path": "a.txt", "mode": "replace", "content": "satu\ndua\n"}]
    )
    assert (tmp_path / "a.txt").read_text() == "satu\ndua\n"
    patch = (
        "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n satu\n-dua\n+dua-baru\n"
    )
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert (tmp_path / "a.txt").read_text() == "satu\ndua-baru\n"


def test_apply_files_traversal_tidak_menulis(tmp_path):
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path, [{"path": "../../etc/passwd", "mode": "replace", "content": "x"}]
        )
    assert not (tmp_path / "passwd").exists()
    assert not list(tmp_path.iterdir())  # tidak ada file apa pun yang ditulis


def test_apply_patch_rusak_ditolak(tmp_path):
    (tmp_path / "a.txt").write_text("satu\n")
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path,
            [{"path": "a.txt", "mode": "patch", "content": "@@ -5,1 +5,1 @@\n-x\n+y\n"}],
        )
    assert (tmp_path / "a.txt").read_text() == "satu\n"


def test_native_messaging_roundtrip():
    payload = {"command": "status"}
    encoded = host_mod.encode_message(payload)
    decoded, rest = host_mod.decode_message(encoded)
    assert decoded == payload
    assert rest == b""


def test_decode_message_buffer_belum_lengkap():
    with pytest.raises(ValueError):
        host_mod.decode_message(b"\x05\x00")


def test_host_perintah_tidak_dikenal():
    assert host_mod.handle_command({"command": "hapus_semua"})["ok"] is False


def test_host_status_mode_manual():
    result = host_mod.handle_command({"command": "status"})
    assert result["ok"] is True
    assert result["mode"] == "manual_handoff"
    assert "docker_available" in result


def test_commit_tanpa_token_ditolak(tmp_path):
    result = host_mod.handle_command(
        {"command": "commit", "worktree": str(tmp_path), "message": "x"}
    )
    assert result["ok"] is False
    assert "approval" in result["error"].lower()


def test_commit_dengan_token_sekali_pakai(tmp_path):
    host = host_mod.RunnerHost(approval_token="token-rahasia-sekali")
    # Bukan repo git -> commit gagal di level git, tapi token sudah terpakai.
    first = host.handle_command(
        {"command": "commit", "worktree": str(tmp_path), "message": "x",
         "approval_token": "token-rahasia-sekali"}
    )
    assert first["ok"] is True  # token valid -> perintah diteruskan (git gagal = False)
    assert first["committed"] is False
    second = host.handle_command(
        {"command": "commit", "worktree": str(tmp_path), "message": "x",
         "approval_token": "token-rahasia-sekali"}
    )
    assert second["ok"] is False  # token sudah dipakai 1x


def test_sandbox_tanpa_docker_jujur():
    result = sandbox_mod.run_in_sandbox("mufakat-sandbox", "/tmp", "echo hi")
    if not sandbox_mod.docker_available():
        assert result["verified"] is False
        assert result["exit_code"] == 127
    else:  # pragma: no cover - Docker ada di host ini
        assert result["verified"] is True


def test_verdict_eskalasi():
    results = [{"tool": "pytest", "passed": True, "findings": []}]
    normal = verdict_mod.apply_verdict(results)
    assert normal["status"] == "AMAN"
    escalated = verdict_mod.apply_verdict(results, escalate=True)
    assert escalated["status"] == "ESKALASI"
    assert escalated["safe"] is False


def test_install_host_manifest_hanya_id_ekstensi():
    manifest = host_manifest("chrome-extension://abcdef/", "/usr/bin/python3")
    assert manifest["allowed_origins"] == ["chrome-extension://abcdef/"]
    assert manifest["name"] == "com.mufakat.runner"
    with pytest.raises(ValueError):
        host_manifest("https://evil.example/", "/usr/bin/python3")


def test_mcp_room_status_tidak_ada_room(tmp_path):
    from mufakat_runner import mcp_server

    result = mcp_server.room_status(str(tmp_path))
    assert result["room_found"] is False
    assert result["mode"] == "manual_handoff"
