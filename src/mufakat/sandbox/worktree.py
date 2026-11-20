"""Git worktree per run (T9).

``create_worktree(repo_path, run_id)`` membuat worktree
``runs/<run_id>/wt`` di branch ``mufakat/<run_id>``. Bila git gagal
(bukan repo, git tidak ada, branch sudah ada), fallback: buat folder
biasa dan kembalikan path-nya — tidak pernah raise untuk kegagalan
git yang sudah diantisipasi.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def create_worktree(repo_path, run_id: str) -> Path:
    """Buat worktree (atau folder biasa bila git gagal)."""
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
    """Hapus worktree; True bila path sudah tidak ada sesudahnya."""
    target = Path(path)
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
    if target.exists():
        try:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError:
            pass
    return not target.exists()
