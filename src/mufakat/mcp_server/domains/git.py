"""Domain git — status/diff/branch read-only, worktree/commit terkendali.

Permission: ``read`` untuk status/diff/branch, ``write-sandbox``
untuk worktree (hanya di bawah ``runs/``), ``approval-required``
untuk commit — commit tanpa approval yang tercatat dan disetujui
ditolak mentah-mentah. Tool ini TIDAK pernah push.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mufakat.mcp_server import approval_store
from mufakat.mcp_server.tools import err, git_status_safe, ok
from mufakat.runner import utcnow

DOMAIN = "git"

CONTRACTS = [
    {"name": "git_status", "description": "Status git read-only.",
     "permission": "read", "scope": "git"},
    {"name": "git_diff", "description": "Diff (stat + patch) read-only.",
     "permission": "read", "scope": "git"},
    {"name": "git_branch", "description": "Daftar branch read-only.",
     "permission": "read", "scope": "git"},
    {"name": "git_create_worktree", "description": "Buat worktree di bawah runs/.",
     "permission": "write-sandbox", "scope": "git"},
    {"name": "git_commit", "description": "Commit — wajib approval yang disetujui.",
     "permission": "approval-required", "scope": "git"},
]


def git_status(repo_path: str = ".") -> dict:
    """Status git read-only untuk sebuah repo lokal."""
    return git_status_safe(repo_path)


def _git(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", repo_path, *args], capture_output=True, text=True,
        timeout=60, shell=False,
    )


def git_diff(repo_path: str = ".", max_chars: int = 20000) -> dict:
    """Diff read-only: ringkasan stat + patch (dibatasi panjangnya)."""
    target = Path(repo_path)
    if not target.is_dir():
        return err("Folder repo tidak ditemukan.", repo_path=repo_path)
    try:
        stat = _git(repo_path, "diff", "--stat")
        patch = _git(repo_path, "diff")
    except Exception as exc:  # noqa: BLE001
        return err(f"git gagal dijalankan: {exc}", repo_path=repo_path)
    if stat.returncode != 0:
        return err("Bukan repositori git atau git error.",
                   repo_path=repo_path, stderr=stat.stderr[:2000])
    return ok(repo_path=repo_path, stat=stat.stdout,
              patch=patch.stdout[:max_chars])


def git_branch(repo_path: str = ".") -> dict:
    """Daftar branch read-only."""
    target = Path(repo_path)
    if not target.is_dir():
        return err("Folder repo tidak ditemukan.", repo_path=repo_path)
    try:
        proc = _git(repo_path, "branch", "--list")
    except Exception as exc:  # noqa: BLE001
        return err(f"git gagal dijalankan: {exc}", repo_path=repo_path)
    if proc.returncode != 0:
        return err("Bukan repositori git atau git error.",
                   repo_path=repo_path, stderr=proc.stderr[:2000])
    branches = [line.strip().lstrip("* ").strip()
                for line in proc.stdout.splitlines() if line.strip()]
    return ok(repo_path=repo_path, branches=branches)


def git_create_worktree(repo_path: str, worktree_path: str,
                        branch: str = "") -> dict:
    """Buat git worktree — hanya di bawah folder ``runs/``."""
    target = Path(worktree_path)
    runs_root = Path("runs").resolve()
    try:
        resolved = target.resolve()
    except OSError as exc:
        return err(f"Path worktree tidak valid: {exc}")
    if runs_root not in resolved.parents and resolved != runs_root:
        return err("Worktree hanya boleh dibuat di bawah runs/.",
                   worktree_path=worktree_path)
    args = ["worktree", "add", str(resolved)]
    if branch:
        args += ["-b", branch]
    try:
        proc = subprocess.run(["git", "-C", repo_path, *args],
                              capture_output=True, text=True, timeout=120,
                              shell=False)
    except Exception as exc:  # noqa: BLE001
        return err(f"git gagal dijalankan: {exc}", repo_path=repo_path)
    if proc.returncode != 0:
        return err("git worktree gagal.", stderr=proc.stderr[:2000])
    return ok(repo_path=repo_path, worktree_path=str(resolved), branch=branch)


def git_commit(repo_path: str, message: str, approval_id: str = "",
               approval_token: str = "") -> dict:
    """Commit — ditolak kecuali ada approval manusia yang disetujui.

    Syarat (H1): approval berstatus ``approved`` di SQLite, token
    sekali pakai valid & belum dipakai & belum kedaluwarsa, dan hash
    ``git diff`` saat ini sama dengan hash saat disetujui. Token
    hangus setelah commit berhasil.
    """
    current_hash = approval_store.diff_hash_for_repo(repo_path)
    valid, reason = approval_store.verify_token(
        approval_id, approval_token, current_diff_hash=current_hash)
    if not valid:
        return err(
            "Commit memerlukan approval manusia yang disetujui. "
            "Minta approval lewat approval_request, setujui lewat "
            "`mufakat approve <id>` (manusia, di TTY), lalu ulangi "
            "dengan approval_id + approval_token sekali pakai. "
            f"Alasan: {reason}",
            approval_id=approval_id)
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", message],
            capture_output=True, text=True, timeout=60, shell=False)
    except Exception as exc:  # noqa: BLE001
        return err(f"git gagal dijalankan: {exc}", repo_path=repo_path)
    if proc.returncode != 0:
        return err("git commit gagal.", stderr=proc.stderr[:2000],
                   stdout=proc.stdout[:2000])
    approval_store.consume_token(approval_id)
    return ok(repo_path=repo_path, message=message,
              approval_id=approval_id, output=proc.stdout[:2000],
              committed_at=utcnow())


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain git ke ``mcp``."""
    for fn in (git_status, git_diff, git_branch, git_create_worktree,
               git_commit):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
