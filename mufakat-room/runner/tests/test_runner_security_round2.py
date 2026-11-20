"""Test regresi audit putaran 2 — Local Runner (pekerja 2).

- N3: `register_repo` TIDAK tersedia lewat native messaging (hanya
  CLI lokal `mufakat-room-runner register`); HOME tidak bisa
  didaftarkan; token approval HANYA terbit setelah manusia
  mengonfirmasi kode 6 digit dari dialog OS (request_approval ->
  confirm_approval -> issue_approval_token).
- GPT 3 (runner): token terikat branch + worktree + hash; pemakaian
  bersamaan ditolak (sekali pakai).
- N9: install_host memakai console script venv (path absolut);
  wrapper executable.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mufakat_runner import host as host_mod
from mufakat_runner import registry as registry_mod

_install_host_path = Path(__file__).resolve().parent.parent / "install_host.py"
_spec = importlib.util.spec_from_file_location(
    "mufakat_room_install_host_r2", _install_host_path)
_install_host = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_install_host)


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.t"],
                   check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Tes"],
                   check=True)
    (repo / "a.txt").write_text("satu\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "awal"],
                   check=True)


def _setup_git_host(tmp_path, monkeypatch):
    """Host + repo git terdaftar + worktree r1 dengan perubahan."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    assert registry_mod.register_repo("r", str(repo))["name"] == "r"
    host = host_mod.RunnerHost()
    assert host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "r1"}
    )["ok"] is True
    wt = repo / "runs" / "r1" / "wt"
    (wt / "a.txt").write_text("satu\ndua\n", encoding="utf-8")
    return host, repo, wt


def _capture_code(monkeypatch):
    """Tangani dialog OS: tangkap kode 6 digit dari body dialog."""
    captured: dict = {}

    def _fake_dialog(title, body):
        captured["body"] = body
        return "dialog"

    monkeypatch.setattr(host_mod, "_show_human_code", _fake_dialog)
    return captured


def _code_from(captured: dict) -> str:
    match = re.search(r"KODE PERSETUJUAN: (\d{6})", captured["body"])
    assert match is not None, captured
    return match.group(1)


# ---------------------------------------------------------------------------
# N3 — register_repo hanya via CLI lokal
# ---------------------------------------------------------------------------
def test_n3_register_repo_lewat_native_messaging_ditolak(tmp_path, monkeypatch):
    """N3 (PoC): pesan `register_repo` apa pun — termasuk HOME —
    ditolak dan mengarahkan ke CLI lokal."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    host = host_mod.RunnerHost()
    res = host.handle_command(
        {"command": "register_repo", "name": "home",
         "path": str(Path.home())})
    assert res["ok"] is False
    assert "mufakat-room-runner register" in res["error"]
    assert registry_mod.load_registry()["repos"] == {}


def test_n3_register_repo_cli_lokal(tmp_path, monkeypatch, capsys):
    """N3: `mufakat-room-runner register <nama> <path>` mendaftarkan
    repo; HOME ditolak."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    assert host_mod.main(["register", "r", str(repo)]) == 0
    assert registry_mod.load_registry()["repos"]["r"] == str(repo.resolve())
    # HOME ditolak oleh CLI.
    assert host_mod.main(["register", "home", str(Path.home())]) == 1
    assert "home" not in registry_mod.load_registry()["repos"]
    capsys.readouterr()


def test_n3_registry_tolak_home(tmp_path, monkeypatch):
    """N3: registry.register_repo menolak HOME dan leluhurnya."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    with pytest.raises(ValueError):
        registry_mod.register_repo("home", str(Path.home()))
    with pytest.raises(ValueError):
        registry_mod.register_repo("root", "/")


# ---------------------------------------------------------------------------
# N3 + GPT 3 — alur persetujuan manusia (kode 6 digit)
# ---------------------------------------------------------------------------
def test_n3_token_tanpa_konfirmasi_manusia_ditolak(tmp_path, monkeypatch):
    """N3 (PoC audit): urutan diff -> issue_approval_token -> commit
    oleh pemanggil yang sama TANPA manusia kini ditolak."""
    host, _repo, _wt = _setup_git_host(tmp_path, monkeypatch)
    shown = host.handle_command({"command": "diff", "run_id": "r1"})
    assert shown["ok"] is True and shown["diff_hash"]
    assert host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": shown["diff_hash"]})["ok"] is False
    assert host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": "apa-pun"})["ok"] is False


def test_n3_alur_kode_6_digit_lengkap(tmp_path, monkeypatch):
    """N3/GPT 3: request -> kode salah ditolak -> kode benar dari
    dialog OS -> token terbit -> commit sekali -> token hangus."""
    host, _repo, wt = _setup_git_host(tmp_path, monkeypatch)
    captured = _capture_code(monkeypatch)
    requested = host.handle_command({"command": "request_approval",
                                     "run_id": "r1"})
    assert requested["ok"] is True
    assert "approval_token" not in requested
    assert "KODE" not in str(requested)  # kode tidak lewat kanal ekstensi
    approval_id = requested["approval_id"]
    assert requested["diff_hash"]
    assert requested["branch"]
    code = _code_from(captured)
    assert re.fullmatch(r"\d{6}", code)
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": approval_id, "code": "000000"})["ok"] is False
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": approval_id, "code": code})["ok"] is True
    issued = host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": requested["diff_hash"]})
    assert issued["ok"] is True
    token = issued["approval_token"]
    assert host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": token})["ok"] is True
    assert host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "y",
         "approval_token": token})["ok"] is False


def test_n3_request_approval_tanpa_diff_ditolak(tmp_path, monkeypatch):
    """GPT 3: approval tanpa perubahan (hash kosong) ditolak."""
    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    registry_mod.register_repo("r", str(repo))
    host = host_mod.RunnerHost()
    host.handle_command({"command": "init_workspace", "repo": "r",
                         "run_id": "r1"})
    res = host.handle_command({"command": "request_approval", "run_id": "r1"})
    assert res["ok"] is False


def test_n3_diff_berubah_setelah_confirm_token_tidak_terbit(
        tmp_path, monkeypatch):
    """GPT 3: diff berubah setelah confirm_approval -> token tidak terbit."""
    host, _repo, wt = _setup_git_host(tmp_path, monkeypatch)
    captured = _capture_code(monkeypatch)
    requested = host.handle_command({"command": "request_approval",
                                     "run_id": "r1"})
    assert requested["ok"] is True
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": requested["approval_id"],
         "code": _code_from(captured)})["ok"] is True
    (wt / "a.txt").write_text("satu\ndua\ntiga\n", encoding="utf-8")
    assert host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": requested["diff_hash"]})["ok"] is False


# ---------------------------------------------------------------------------
# N9 — wrapper + install_host
# ---------------------------------------------------------------------------
def test_n9_wrapper_executable():
    """N9: wrapper mufakat-runner-host punya bit executable."""
    wrapper = Path(__file__).resolve().parent.parent / "mufakat-runner-host"
    assert wrapper.is_file()
    assert os.access(wrapper, os.X_OK)
    assert "VIRTUAL_ENV" in wrapper.read_text(encoding="utf-8")


def test_n9_install_host_pakai_console_script_venv(tmp_path, monkeypatch):
    """N9: install_host memakai console script dari venv (path absolut),
    bukan python3 dari PATH."""
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    script = venv_bin / "mufakat-runner-host"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    fake_python = venv_bin / "python"
    fake_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(fake_python))
    monkeypatch.setenv("PATH", str(venv_bin), prepend=os.pathsep)
    default = _install_host.default_host_path()
    assert default == str(script.resolve())
    assert Path(default).is_absolute()
    assert default != sys.executable


def test_n9_host_manifest_tolak_path_relatif():
    """N9: manifest menolak host-path relatif (harus absolut)."""
    with pytest.raises(ValueError):
        _install_host.host_manifest("chrome-extension://abcdef/",
                                    "mufakat-runner-host")
