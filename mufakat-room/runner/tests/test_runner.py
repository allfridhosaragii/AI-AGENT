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


# -- Regresi audit ekstrem Putaran 1 (20 Nov 2026) -----------------------
def test_path_drive_windows_dan_nul_ditolak():
    for bad in ("C:\\Windows\\x.txt", "C:/Windows/x.txt", "a\x00b"):
        with pytest.raises(ValueError):
            worktree_mod.validate_rel_path(bad)


def test_apply_files_symlink_dir_ditolak(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path, [{"path": "link/evil.txt", "mode": "replace", "content": "x"}]
        )
    assert not (outside / "evil.txt").exists()


def test_apply_files_symlink_file_ditolak(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("asli")
    (tmp_path / "f.txt").symlink_to(target)
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path, [{"path": "f.txt", "mode": "replace", "content": "x"}]
        )
    assert target.read_text() == "asli"


def test_apply_files_atomik_semua_divalidasi_dulu(tmp_path):
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path,
            [{"path": "good.txt", "mode": "replace", "content": "g"},
             {"path": "../../etc/passwd", "mode": "replace", "content": "x"}],
        )
    assert not (tmp_path / "good.txt").exists()
    with pytest.raises(ValueError):
        worktree_mod.apply_files(
            tmp_path,
            [{"path": "good2.txt", "mode": "tidak_ada", "content": "g"}],
        )
    assert not (tmp_path / "good2.txt").exists()


def test_apply_patch_konteks_salah_ditolak(tmp_path):
    (tmp_path / "a.txt").write_text("satu\ndua\n")
    patch = "@@ -1,2 +1,2 @@\n SALAH_KONTEKS\n-dua\n+dua-baru\n"
    with pytest.raises(ValueError):
        worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert (tmp_path / "a.txt").read_text() == "satu\ndua\n"


def test_apply_patch_hapus_salah_ditolak(tmp_path):
    (tmp_path / "a.txt").write_text("satu\ndua\n")
    patch = "@@ -1,2 +1,2 @@\n satu\n-TIDAK_ADA\n+baru\n"
    with pytest.raises(ValueError):
        worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert (tmp_path / "a.txt").read_text() == "satu\ndua\n"


def test_apply_patch_jumlah_baris_tidak_cocok_ditolak(tmp_path):
    (tmp_path / "a.txt").write_text("satu\ndua\n")
    # Header bilang 2 baris lama, isi hanya 1 baris konteks.
    patch = "@@ -1,2 +1,1 @@\n satu\n"
    with pytest.raises(ValueError):
        worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])


def test_apply_patch_kosong_ditolak(tmp_path):
    (tmp_path / "a.txt").write_text("satu\n")
    with pytest.raises(ValueError):
        worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": "  "}])
    assert (tmp_path / "a.txt").read_text() == "satu\n"


def test_apply_patch_penanda_no_newline_diterima(tmp_path):
    (tmp_path / "a.txt").write_text("satu\ndua\n")
    patch = "@@ -1,2 +1,2 @@\n satu\n-dua\n+dua\n\\ No newline at end of file\n"
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert (tmp_path / "a.txt").read_text() == "satu\ndua\n"


def test_host_pesan_tipe_salah_tidak_crash(tmp_path):
    assert host_mod.handle_command(
        {"command": "apply_files", "worktree": str(tmp_path), "files": "bukan-list"}
    )["ok"] is False
    assert host_mod.handle_command(
        {"command": "init_workspace", "repo_path": 123, "run_id": "x"}
    )["ok"] is False
    assert host_mod.handle_command(
        {"command": "apply_files", "worktree": str(tmp_path)}
    )["ok"] is True


def test_host_init_workspace_run_id_traversal_ditolak(tmp_path):
    result = host_mod.handle_command(
        {"command": "init_workspace", "repo_path": str(tmp_path), "run_id": "../../evil"}
    )
    assert result["ok"] is False


def test_decode_message_pesan_raksasa_ditolak():
    import struct

    with pytest.raises(ValueError):
        host_mod.decode_message(struct.pack("<I", 0xFFFFFFFF) + b"x")


def test_cleanup_path_berbahaya_ditolak():
    from pathlib import Path as _P

    assert worktree_mod.cleanup("/") is False
    assert worktree_mod.cleanup(str(_P.home())) is False


def test_install_host_manifest_id_tidak_valid_ditolak():
    for bad in ("chrome-extension://abc/extra", "chrome-extension://",
                "https://evil.example/", "chrome-extension://ABC/"):
        with pytest.raises(ValueError):
            _install_host.host_manifest(bad, "/usr/bin/python3")


def test_mcp_room_status_json_bukan_object(tmp_path):
    from mufakat_runner import mcp_server

    (tmp_path / "room.json").write_text("[1, 2]")
    result = mcp_server.room_status(str(tmp_path))
    assert result["ok"] is False
    assert result["room_found"] is False


def test_round2_cleanup_worktree_sah_dalam_repo_boleh(tmp_path):
    repo = tmp_path / "repo"
    wt = repo / "runs" / "r1" / "wt"
    wt.mkdir(parents=True)
    assert worktree_mod.cleanup(wt, repo) is True
    assert not wt.exists()


def test_round2_cleanup_leluhur_repo_ditolak(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert worktree_mod.cleanup(tmp_path, repo) is False
    assert tmp_path.exists()


def test_round2_install_host_path_kosong_ditolak():
    with pytest.raises(ValueError):
        _install_host.host_manifest("chrome-extension://abcdef/", "")
