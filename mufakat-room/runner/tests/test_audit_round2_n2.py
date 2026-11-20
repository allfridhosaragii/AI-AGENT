"""Test regresi audit putaran 2 — N2 (runner worktree diff/commit)
+ N7 (status runner jujur).

PoC N2 (laporan audit): ``apply_files`` mengubah ``app.py`` +
menambah ``backdoor.py``. Dulu diff yang ditampilkan TIDAK memuat
``backdoor.py`` (``git diff HEAD`` melewatkan untracked), tapi
``commit`` (``git add -A``) ikut meng-commit-nya. Sekarang:

- ``diff()`` stage dulu (``git add -A``) lalu
  ``git diff --cached HEAD`` — file baru WAJIB muncul di diff
  yang disetujui.
- ``commit()`` TANPA ``git add -A`` lagi, memverifikasi ulang hash
  ``--cached`` yang disetujui, dan memeriksa staged diff kosong
  setelah commit.
- Artefak gate (``coverage.json`` dkk.) ditulis di luar worktree
  (N4, gate pytest) sehingga tidak ikut ter-stage/ter-commit.

N7: ``status`` runner melapor ``docker_available`` jujur — False
bila daemon mati / image tidak ada (mock, bukan ``shutil.which``).
"""

from __future__ import annotations

import subprocess

from mufakat_runner import host as host_mod
from mufakat_runner import sandbox as sandbox_mod
from mufakat_runner import worktree as worktree_mod


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _init_repo(tmp_path):
    """Repo git dengan satu commit awal; kembalikan path repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "t@t.t", cwd=repo)
    _git("config", "user.name", "Tes", cwd=repo)
    (repo / "app.py").write_text("print('v1')\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "awal", cwd=repo)
    return repo


def _committed_files(worktree):
    out = subprocess.run(
        ["git", "show", "--name-only", "--format=", "HEAD"],
        cwd=str(worktree), capture_output=True, text=True, check=True)
    return sorted(n for n in out.stdout.splitlines() if n.strip())


# ---------------------------------------------------------------------------
# N2 — diff memuat file baru; commit hanya yang disetujui
# ---------------------------------------------------------------------------
def test_n2_diff_memuat_file_baru_untracked(tmp_path):
    """PoC N2: backdoor.py (untracked) WAJIB muncul di diff."""
    repo = _init_repo(tmp_path)
    wt = repo / "runs" / "r1" / "wt"
    worktree_mod.init_workspace(repo, "r1")
    worktree_mod.apply_files(wt, [
        {"path": "app.py", "mode": "replace",
         "content": "print('v2')\n"},
        {"path": "backdoor.py", "mode": "replace",
         "content": "import os\nos.system('id')\n"},
    ])
    diff = worktree_mod.diff(wt)
    assert "backdoor.py" in diff
    assert "app.py" in diff
    assert "os.system" in diff
    assert worktree_mod.diff_hash(wt)


def test_n2_commit_hanya_file_yang_ada_di_diff(tmp_path):
    """Yang di-commit = yang ada di diff yang disetujui, tidak lebih."""
    repo = _init_repo(tmp_path)
    worktree_mod.init_workspace(repo, "r1")
    wt = repo / "runs" / "r1" / "wt"
    worktree_mod.apply_files(wt, [
        {"path": "app.py", "mode": "replace", "content": "print('v2')\n"},
        {"path": "backdoor.py", "mode": "replace",
         "content": "import os\nos.system('id')\n"},
    ])
    shown_hash = worktree_mod.diff_hash(wt)
    assert shown_hash
    assert worktree_mod.commit(wt, "perubahan disetujui",
                               expected_diff_hash=shown_hash) is True
    assert _committed_files(wt) == ["app.py", "backdoor.py"]


def test_n2_commit_tolak_bila_diff_berubah_setelah_approve(tmp_path):
    """File ditambahkan SETELAH diff disetujui -> commit ditolak."""
    repo = _init_repo(tmp_path)
    worktree_mod.init_workspace(repo, "r1")
    wt = repo / "runs" / "r1" / "wt"
    worktree_mod.apply_files(wt, [
        {"path": "app.py", "mode": "replace", "content": "print('v2')\n"},
    ])
    shown_hash = worktree_mod.diff_hash(wt)
    # Penyelundupan setelah Approve: file baru muncul diam-diam.
    (wt / "backdoor.py").write_text("import os\nos.system('id')\n",
                                    encoding="utf-8")
    assert worktree_mod.commit(wt, "x",
                               expected_diff_hash=shown_hash) is False
    # Tidak ada commit baru yang terjadi.
    out = subprocess.run(["git", "log", "--oneline"], cwd=str(wt),
                         capture_output=True, text=True, check=True)
    assert len(out.stdout.strip().splitlines()) == 1


def test_n2_commit_tanpa_diff_dulu_tidak_staging_diam_diam(tmp_path):
    """commit() tanpa diff() sebelumnya: tidak ada yang ter-stage
    -> git commit gagal (False), bukan commit diam-diam."""
    repo = _init_repo(tmp_path)
    worktree_mod.init_workspace(repo, "r1")
    wt = repo / "runs" / "r1" / "wt"
    (wt / "app.py").write_text("print('v2')\n", encoding="utf-8")
    assert worktree_mod.commit(wt, "x") is False


def test_n2_alur_host_backdoor_tidak_lolos_diam_diam(tmp_path, monkeypatch):
    """Alur host lengkap: apply -> diff (lihat backdoor) -> approve
    manusia (kode 6 digit) -> token -> commit berisi tepat diff itu."""
    import re as _re

    from mufakat_runner import registry as registry_mod

    monkeypatch.setenv("MUFAKAT_RUNNER_REGISTRY",
                       str(tmp_path / "runner.json"))
    repo = _init_repo(tmp_path)
    assert registry_mod.register_repo("r", str(repo))["name"] == "r"
    host = host_mod.RunnerHost()
    assert host.handle_command(
        {"command": "init_workspace", "repo": "r", "run_id": "r1"}
    )["ok"] is True
    wt = repo / "runs" / "r1" / "wt"
    assert host.handle_command(
        {"command": "apply_files", "run_id": "r1",
         "files": [
             {"path": "app.py", "mode": "replace",
              "content": "print('v2')\n"},
             {"path": "backdoor.py", "mode": "replace",
              "content": "import os\nos.system('id')\n"},
         ]})["ok"] is True
    shown = host.handle_command({"command": "diff", "run_id": "r1"})
    assert shown["ok"] is True
    # Manusia HARUS melihat backdoor.py di diff sebelum menyetujui.
    assert "backdoor.py" in shown["diff"]
    captured: dict = {}

    def _fake_dialog(title, body):
        captured["body"] = body
        return "dialog"

    monkeypatch.setattr(host_mod, "_show_human_code", _fake_dialog)
    requested = host.handle_command({"command": "request_approval",
                                     "run_id": "r1"})
    assert requested["ok"] is True
    code = _re.search(r"KODE PERSETUJUAN: (\d{6})",
                      captured["body"]).group(1)
    assert host.handle_command(
        {"command": "confirm_approval", "run_id": "r1",
         "approval_id": requested["approval_id"], "code": code}
    )["ok"] is True
    issued = host.handle_command(
        {"command": "issue_approval_token", "run_id": "r1",
         "diff_hash": shown["diff_hash"]})
    assert issued["ok"] is True
    committed = host.handle_command(
        {"command": "commit", "run_id": "r1", "message": "x",
         "approval_token": issued["approval_token"]})
    assert committed["ok"] is True
    assert committed["committed"] is True
    assert _committed_files(wt) == ["app.py", "backdoor.py"]


def test_n2_artefak_gate_di_luar_worktree_tidak_tercommit(tmp_path):
    """Artefak gate yang (tidak sengaja) ada di worktree TIDAK ikut
    ter-commit bila ditulis di luar worktree — simulasi: coverage
    ditulis ke folder gates di luar wt, diff tidak memuatnya."""
    repo = _init_repo(tmp_path)
    worktree_mod.init_workspace(repo, "r1")
    wt = repo / "runs" / "r1" / "wt"
    gates_dir = repo / "runs" / "r1" / "gates"
    gates_dir.mkdir(parents=True)
    (gates_dir / "coverage.json").write_text('{"totals": {}}',
                                             encoding="utf-8")
    worktree_mod.apply_files(wt, [
        {"path": "app.py", "mode": "replace", "content": "print('v2')\n"},
    ])
    diff = worktree_mod.diff(wt)
    assert "coverage.json" not in diff
    shown_hash = worktree_mod.diff_hash(wt)
    assert worktree_mod.commit(wt, "x",
                               expected_diff_hash=shown_hash) is True
    assert _committed_files(wt) == ["app.py"]


# ---------------------------------------------------------------------------
# N7 — status runner jujur (mock)
# ---------------------------------------------------------------------------
def test_n7_status_docker_available_jujur_daemon_mati(monkeypatch):
    """CLI ada tapi daemon mati -> status docker_available False."""
    import mufakat.sandbox.docker as docker_mod

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker")

    def _fake_run(args, **kwargs):
        cmd = list(args)
        rc = 1 if cmd[:2] == ["docker", "info"] else 0
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")

    monkeypatch.setattr(docker_mod.subprocess, "run", _fake_run)
    assert sandbox_mod.docker_available() is False
    result = host_mod.handle_command({"command": "status"})
    assert result["ok"] is True
    assert result["docker_available"] is False
