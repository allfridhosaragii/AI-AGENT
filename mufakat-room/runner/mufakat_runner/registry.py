"""Registry Local Runner (audit 20 Nov 2026: C2).

Satu file milik pengguna: ``~/.mufakat/runner.json`` (bisa di-override
env ``MUFAKAT_RUNNER_REGISTRY`` untuk test):

.. code-block:: json

    {"repos": {"nama-repo": "/abs/path/repo"},
     "runs": {"<run_id>": {"repo": "nama-repo",
                           "worktree": "/abs/path/repo/runs/<run_id>/wt"}}}

- Repo HANYA boleh dari registry ini (didaftarkan sekali lewat
  perintah ``register_repo``) — pesan native messaging TIDAK BOLEH
  membawa path repo bebas.
- Semua perintah host lain hanya menerima ``run_id``; worktree
  diambil dari registry, bukan dari pesan.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = [
    "registry_path", "load_registry", "save_registry",
    "register_repo", "resolve_repo", "record_run", "resolve_run",
    "remove_run",
]


def registry_path() -> Path:
    """Lokasi file registry (env override untuk test)."""
    override = os.environ.get("MUFAKAT_RUNNER_REGISTRY", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".mufakat" / "runner.json"


def load_registry() -> dict:
    """Baca registry; {} terstruktur bila file belum ada / rusak."""
    path = registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"repos": {}, "runs": {}}
    if not isinstance(data, dict):
        return {"repos": {}, "runs": {}}
    data.setdefault("repos", {})
    data.setdefault("runs", {})
    if not isinstance(data["repos"], dict):
        data["repos"] = {}
    if not isinstance(data["runs"], dict):
        data["runs"] = {}
    return data


def save_registry(data: dict) -> Path:
    """Tulis registry (atomik-ish: tulis lalu ganti)."""
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(path)
    return path


def register_repo(name: str, repo_path: str | Path) -> dict:
    """Daftarkan satu repo milik pengguna (nama -> path absolut).

    Nama hanya ``[A-Za-z0-9][A-Za-z0-9._-]*``; path harus folder yang ada.
    """
    import re

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError(f"Nama repo tidak valid: {name!r}")
    resolved = Path(repo_path).resolve()
    if not resolved.is_dir():
        raise ValueError(f"Repo tidak ditemukan: {repo_path!r}")
    # Audit putaran 2 (N3): HOME (atau leluhurnya, mis. /) tidak boleh
    # didaftarkan — PoC mendaftarkan HOME lewat pesan native messaging.
    home = Path.home().resolve()
    if resolved == home or resolved in home.parents:
        raise ValueError(
            f"Repo tidak boleh HOME atau leluhur HOME: {resolved}")
    data = load_registry()
    data["repos"][name] = str(resolved)
    save_registry(data)
    return {"name": name, "path": str(resolved)}


def resolve_repo(repo: str | Path) -> Path | None:
    """Kembalikan path repo bila terdaftar, else None.

    ``repo`` boleh berupa nama terdaftar atau path yang persis sama
    dengan nilai terdaftar. Path bebas yang tidak terdaftar DITOLAK.
    """
    if repo is None:
        return None
    data = load_registry()
    repos = data.get("repos", {})
    if isinstance(repo, str) and repo in repos:
        candidate = Path(repos[repo])
        return candidate if candidate.is_dir() else None
    try:
        resolved = Path(repo).resolve()
    except OSError:
        return None
    for value in repos.values():
        try:
            if resolved == Path(value).resolve():
                return resolved
        except OSError:
            continue
    return None


def record_run(run_id: str, repo_name: str, worktree: str | Path) -> None:
    """Catat ``run_id -> worktree`` di registry."""
    data = load_registry()
    data["runs"][str(run_id)] = {
        "repo": repo_name,
        "worktree": str(Path(worktree).resolve()),
    }
    save_registry(data)


def resolve_run(run_id: str) -> dict | None:
    """Kembalikan ``{"repo", "worktree"}`` untuk run_id, else None."""
    if not isinstance(run_id, str):
        return None
    return load_registry().get("runs", {}).get(run_id)


def remove_run(run_id: str) -> None:
    """Hapus catatan run dari registry."""
    data = load_registry()
    data.get("runs", {}).pop(str(run_id), None)
    save_registry(data)
