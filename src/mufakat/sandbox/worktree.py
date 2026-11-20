"""Git worktree per run (T9).

``create_worktree(repo_path, run_id)`` membuat worktree
``runs/<run_id>/wt`` di branch ``mufakat/<run_id>``. Bila git gagal
(bukan repo, git tidak ada, branch sudah ada), fallback: buat folder
biasa dan kembalikan path-nya — tidak pernah raise untuk kegagalan
git yang sudah diantisipasi.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_run_id(run_id: str) -> str:
    """Validasi ``run_id``: satu segmen path yang aman.

    Dulu ``run_id`` seperti ``../../evil`` lolos dan membuat folder
    di luar repo (``runs/../../evil/wt``) sekaligus nama branch yang
    tidak valid.
    """
    if not isinstance(run_id, str) or not _RUN_ID_RE.match(run_id) or ".." in run_id:
        raise ValueError(f"run_id tidak valid: {run_id!r}")
    return run_id


def _is_dangerous_target(target: Path, repo_path: Path | None) -> bool:
    """True bila ``target`` tidak boleh dihapus: root, home, repo itu
    sendiri, atau leluhur repo. Mencegah ``cleanup("/")`` / ``cleanup(home)``
    menghapus sistem lewat ``shutil.rmtree``."""
    try:
        resolved = target.resolve()
    except OSError:
        return True
    if resolved == Path("/"):
        return True
    home = Path.home()
    if resolved == home:
        return True
    if repo_path is not None:
        try:
            repo_resolved = Path(repo_path).resolve()
        except OSError:
            repo_resolved = None
        # Berbahaya bila target ADALAH repo atau LELUHUR repo (menghapus
        # target ikut menghapus repo). Target DI DALAM repo (mis.
        # runs/<id>/wt) justru worktree sah yang BOLEH dihapus.
        # (Audit Putaran 2: kondisi ini sempat tertulis terbalik —
        # worktree sah ditolak, leluhur repo malah terhapus.)
        if repo_resolved is not None and (
            resolved == repo_resolved or resolved in repo_resolved.parents
        ):
            return True
    return False


def create_worktree(repo_path, run_id: str) -> Path:
    """Buat worktree (atau folder biasa bila git gagal)."""
    validate_run_id(run_id)
    repo = Path(repo_path)
    target = repo / "runs" / run_id / "wt"
    branch = f"mufakat/{run_id}"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "worktree", "add", str(target), "-b", branch],
            cwd=str(repo), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return target
        # Branch mungkin sudah ada: coba tanpa -b.
        result = subprocess.run(
            ["git", "worktree", "add", str(target), branch],
            cwd=str(repo), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return target
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass
    target.mkdir(parents=True, exist_ok=True)
    return target


def remove_worktree(path, repo_path=None) -> bool:
    """Hapus worktree; True bila path sudah tidak ada sesudahnya.

    Fail-closed: path berbahaya (root/home/repo) TIDAK dihapus dan
    mengembalikan False.
    """
    target = Path(path)
    if _is_dangerous_target(target, Path(repo_path) if repo_path is not None else None):
        return False
    _removed = False
    if repo_path is not None:
        try:
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=str(repo_path), capture_output=True, text=True, timeout=60,
            )
            _removed = result.returncode == 0
            subprocess.run(["git", "worktree", "prune"],
                           cwd=str(repo_path), capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
            _removed = False
    if target.exists() or target.is_symlink():
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError:
            pass
    return not target.exists() and not target.is_symlink()
