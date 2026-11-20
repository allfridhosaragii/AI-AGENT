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


def _setup_host(tmp_path, monkeypatch):
    """Host + repo terdaftar (C2, N3): registrasi HANYA lewat registry
    (setara CLI lokal `mufakat-room-runner register`) — perintah
    native messaging `register_repo` sudah dihapus."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    from mufakat_runner import registry as registry_mod

    assert registry_mod.register_repo("r", str(repo))["name"] == "r"
    host = host_mod.RunnerHost()
    res = host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "r1"})
    assert res["ok"] is True
    return host, repo


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


def test_apply_patch_crlf_baris_plus_pakai_crlf(tmp_path):
    """L5 (putaran 2): file CRLF — baris '+' harus berakhir CRLF, bukan LF."""
    target = tmp_path / "a.txt"
    target.write_bytes(b"satu\r\ndua\r\n")
    # NB: patch_lines di-split tanpa keepends, jadi "+tiga" tanpa \r di teks
    # patch tetap harus menghasilkan baris CRLF karena file aslinya CRLF.
    patch = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,3 @@\n satu\n dua\n+tiga\n"
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert target.read_bytes() == b"satu\r\ndua\r\ntiga\r\n"


def test_apply_patch_tanpa_newline_akhir_dihormati(tmp_path):
    """L5 (putaran 2): penanda '\\ No newline at end of file' setelah baris
    '+' — hasil akhir TIDAK punya newline akhir."""
    target = tmp_path / "a.txt"
    target.write_text("satu\ndua", encoding="utf-8")
    patch = (
        "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n satu\n-dua\n+dua-baru\n"
        "\\ No newline at end of file\n"
    )
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert target.read_text(encoding="utf-8") == "satu\ndua-baru"


def test_apply_patch_tanpa_marker_tambah_newline(tmp_path):
    """L5: tanpa penanda, patch unified diff standar berarti file baru
    berakhir newline (baris '+' terakhir diberi EOL file)."""
    target = tmp_path / "a.txt"
    target.write_text("satu\ndua", encoding="utf-8")
    patch = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n satu\n-dua\n+dua-baru\n"
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert target.read_text(encoding="utf-8") == "satu\ndua-baru\n"


def test_apply_patch_hapus_baris_tanpa_newline_tidak_rusak(tmp_path):
    """L5: penanda setelah baris '-' merujuk ke baris yang DIHAPUS — baris
    konteks sebelumnya tidak boleh kehilangan newline-nya."""
    target = tmp_path / "a.txt"
    target.write_text("satu\ndua", encoding="utf-8")
    patch = (
        "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,1 @@\n satu\n-dua\n\\ No newline at end of file\n"
    )
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert target.read_text(encoding="utf-8") == "satu\n"


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


def test_commit_tanpa_token_ditolak(tmp_path, monkeypatch):
    host, _repo = _setup_host(tmp_path, monkeypatch)
    result = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x"}
    )
    assert result["ok"] is False
    assert "approval" in result["error"].lower()


def test_commit_dengan_token_sekali_pakai(tmp_path, monkeypatch):
    _setup_host(tmp_path, monkeypatch)
    host = host_mod.RunnerHost(approval_token="token-rahasia-sekali")
    # Bukan repo git -> commit gagal di level git, tapi token sudah terpakai.
    first = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": "token-rahasia-sekali"}
    )
    assert first["ok"] is True  # token valid -> perintah diteruskan (git gagal = False)
    assert first["committed"] is False
    second = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": "token-rahasia-sekali"}
    )
    assert second["ok"] is False  # token sudah dipakai 1x


def test_sandbox_tanpa_docker_jujur():
    result = sandbox_mod.run_in_sandbox(  # nosec B108 - "/tmp" hanya argumen workdir dummy untuk test
        "mufakat-sandbox", "/tmp", "echo hi")
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
    # L5 (putaran 2): penanda setelah baris "+" berarti baris baru TIDAK
    # punya newline akhir — dulu penanda diabaikan sehingga hasil tetap
    # "satu\ndua\n" (bug). Ekspektasi diperbaiki ke semantik diff standar.
    (tmp_path / "a.txt").write_text("satu\ndua\n")
    patch = "@@ -1,2 +1,2 @@\n satu\n-dua\n+dua\n\\ No newline at end of file\n"
    worktree_mod.apply_files(tmp_path, [{"path": "a.txt", "mode": "patch", "content": patch}])
    assert (tmp_path / "a.txt").read_text() == "satu\ndua"


def test_host_pesan_tipe_salah_tidak_crash(tmp_path, monkeypatch):
    host, _repo = _setup_host(tmp_path, monkeypatch)
    assert host.handle_command(
        {"command": "apply_files", "run_id": "r1", "files": "bukan-list"}
    )["ok"] is False
    assert host.handle_command(
        {"command": "init_workspace", "repo_path": 123, "run_id": "x"}
    )["ok"] is False
    assert host.handle_command(
        {"command": "apply_files", "run_id": "r1"}
    )["ok"] is True


def test_host_init_workspace_run_id_traversal_ditolak(tmp_path, monkeypatch):
    host, _repo = _setup_host(tmp_path, monkeypatch)
    result = host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "../../evil"}
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


# -- Regresi audit 20 Nov 2026 (C2 + H6) ----------------------------------
def test_host_path_bebas_ditolak_semua_perintah(tmp_path, monkeypatch):
    """C2 (PoC audit): path bebas di luar runs/ ditolak untuk SETIAP
    perintah — apply_files, cleanup, run_gates, diff, commit."""
    host, repo = _setup_host(tmp_path, monkeypatch)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "penting.txt").write_text("jangan hapus", encoding="utf-8")
    for cmd in (
        {"command": "apply_files", "worktree": str(victim),
         "files": [{"path": "x.txt", "mode": "replace", "content": "x"}]},
        {"command": "cleanup", "worktree": str(victim)},
        {"command": "run_gates", "target_dir": str(victim)},
        {"command": "diff", "worktree": str(victim)},
        {"command": "commit", "worktree": str(victim), "message": "x",
         "approval_token": "t"},
        {"command": "apply_files", "run_id": "tidak-ada",
         "files": [{"path": "x.txt", "mode": "replace", "content": "x"}]},
        {"command": "cleanup", "run_id": "tidak-ada"},
        {"command": "run_gates", "run_id": "tidak-ada"},
        {"command": "diff", "run_id": "tidak-ada"},
        {"command": "commit", "run_id": "tidak-ada", "message": "x"},
    ):
        assert host.handle_command(cmd)["ok"] is False, cmd
    assert (victim / "penting.txt").read_text() == "jangan hapus"
    assert victim.exists()


def test_host_init_workspace_repo_belum_terdaftar_ditolak(tmp_path, monkeypatch):
    """C2: repo_path bebas yang tidak ada di registry ditolak."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    host = host_mod.RunnerHost()
    result = host.handle_command(
        {"command": "init_workspace", "repo": str(tmp_path), "run_id": "r1"})
    assert result["ok"] is False
    assert "terdaftar" in result["error"]


def test_host_alur_run_id_lengkap(tmp_path, monkeypatch):
    """C2: alur normal berbasis run_id (init -> apply -> diff -> cleanup)."""
    host, repo = _setup_host(tmp_path, monkeypatch)
    assert host.handle_command(
        {"command": "apply_files", "run_id": "r1",
         "files": [{"path": "a.txt", "mode": "replace", "content": "halo\n"}]}
    )["ok"] is True
    assert (repo / "runs" / "r1" / "wt" / "a.txt").read_text() == "halo\n"
    assert host.handle_command({"command": "diff", "run_id": "r1"})["ok"] is True
    assert host.handle_command({"command": "cleanup", "run_id": "r1"})["ok"] is True
    assert not (repo / "runs" / "r1" / "wt").exists()
    # run_id yang sudah di-cleanup tidak dikenal lagi.
    assert host.handle_command({"command": "diff", "run_id": "r1"})["ok"] is False


def test_host_cleanup_hanya_di_bawah_runs_wt(tmp_path, monkeypatch):
    """C2: cleanup via worktree hanya boleh di bawah runs/<id>/wt."""
    _host, repo = _setup_host(tmp_path, monkeypatch)
    assert worktree_mod.cleanup(repo, repo) is False
    assert repo.exists()
    assert worktree_mod.cleanup(tmp_path, repo) is False
    assert tmp_path.exists()


def test_host_issue_approval_token_terikat_hash_diff(tmp_path, monkeypatch):
    """H6 + N3/GPT 3: token HANYA terbit setelah manusia mengonfirmasi
    lewat kode 6 digit dari dialog OS (bukan dari kanal ekstensi).
    Alur: request_approval -> confirm_approval(kode) ->
    issue_approval_token -> commit sekali; diff berubah -> ditolak."""
    import re
    import subprocess

    from mufakat_runner import registry as registry_mod

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
    assert registry_mod.register_repo("r", str(repo))["name"] == "r"
    host = host_mod.RunnerHost()
    assert host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "r1"}
    )["ok"] is True
    wt = repo / "runs" / "r1" / "wt"
    (wt / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    # N3: issue_approval_token TANPA konfirmasi manusia -> ditolak.
    shown = host.handle_command({"command": "diff", "run_id": "r1"})
    assert shown["ok"] is True and shown["diff_hash"]
    assert host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": shown["diff_hash"]})["ok"] is False
    # Langkah 1: request_approval — kode tampil di dialog OS (ditangkap
    # di test lewat monkeypatch), TIDAK ada di respons.
    captured: dict = {}

    def _fake_dialog(title, body):
        captured["body"] = body
        return "dialog"

    monkeypatch.setattr(host_mod, "_show_human_code", _fake_dialog)
    requested = host.handle_command({"command": "request_approval",
                                     "run_id": "r1"})
    assert requested["ok"] is True
    assert "approval_token" not in requested
    assert "KODE" not in str(requested)
    approval_id = requested["approval_id"]
    assert requested["diff_hash"] == shown["diff_hash"]
    code = re.search(r"KODE PERSETUJUAN: (\d{6})", captured["body"]).group(1)
    # Kode salah -> confirm ditolak; token tetap tidak terbit.
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": approval_id, "code": "000000"})["ok"] is False
    assert host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": shown["diff_hash"]})["ok"] is False
    # Langkah 2: kode benar dari dialog OS -> terkonfirmasi.
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": approval_id, "code": code})["ok"] is True
    # Hash salah -> token tidak terbit.
    bad = host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": "0" * 64})
    assert bad["ok"] is False
    # Langkah 3: token terbit untuk hash yang dikonfirmasi manusia.
    issued = host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": shown["diff_hash"]})
    assert issued["ok"] is True
    token = issued["approval_token"]
    # Diff berubah setelah Approve -> commit ditolak.
    (wt / "a.txt").write_text("satu\ndua\ntiga\n", encoding="utf-8")
    assert host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": token})["ok"] is False
    (wt / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    committed = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": token})
    assert committed["ok"] is True
    # Token sekali pakai.
    assert host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "y",
         "approval_token": token})["ok"] is False


def test_install_host_default_bukan_sys_executable():
    """H6: default host-path adalah wrapper executable, bukan interpreter."""
    import sys

    default = _install_host.default_host_path()
    assert default != sys.executable
    assert default.endswith("mufakat-runner-host")
    with pytest.raises(ValueError):
        _install_host.host_manifest("chrome-extension://abcdef/",
                                    sys.executable)


def test_install_host_menulis_manifest(tmp_path):
    """H6: install() benar-benar menulis file manifest JSON."""
    target = _install_host.install(
        "chrome-extension://abcdef/",
        "/usr/local/bin/mufakat-runner-host",
        manifest_dir=tmp_path, dry_run=False)
    assert target.is_file()
    import json

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["path"] == "/usr/local/bin/mufakat-runner-host"
    assert data["allowed_origins"] == ["chrome-extension://abcdef/"]


def test_mcp_run_gates_dan_gate_report_berbasis_run_id(tmp_path, monkeypatch):
    """C2: MCP runner run_gates/gate_report memakai run_id, bukan path."""
    from mufakat_runner import mcp_server

    host, repo = _setup_host(tmp_path, monkeypatch)
    assert mcp_server.run_gates("tidak-ada")["ok"] is False
    assert mcp_server.gate_report("tidak-ada")["ok"] is False
    assert mcp_server.gate_report("tidak-ada")["found"] is False
    # run_id dikenal: gates jalan (tanpa Docker -> BELUM_TERVERIFIKASI).
    result = mcp_server.run_gates("r1")
    assert result["ok"] is True
    assert result["verdict"]["status"] in ("BELUM_TERVERIFIKASI", "TIDAK AMAN", "AMAN")
    # gate_report sebelum ada verdict.json -> found False.
    assert mcp_server.gate_report("r1")["found"] is False
    # Tulis verdict.json pura-pura di run dir, lalu gate_report menemukannya.
    verdict_dir = repo / "runs" / "r1" / "gates"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    (verdict_dir / "verdict.json").write_text('{"status": "AMAN"}',
                                              encoding="utf-8")
    found = mcp_server.gate_report("r1")
    assert found["found"] is True
    assert found["verdict"]["status"] == "AMAN"
