"""Registry repo terdaftar untuk operasi Git MCP (audit putaran 2: GPT 5).

Satu file milik pengguna, SAMA dengan registry Local Runner
``~/.mufakat/runner.json`` (env ``MUFAKAT_RUNNER_REGISTRY`` untuk
test, atau ``MUFAKAT_REPO_REGISTRY``):

.. code-block:: json

    {"repos": {"nama-repo": "/abs/path/repo"}, "runs": {...}}

Aturan:

- Operasi Git MCP (``git_status`` / ``git_diff`` / ``git_branch`` /
  ``git_create_worktree`` / ``git_commit``) HANYA menerima repo yang
  terdaftar di sini — nama terdaftar, path yang persis sama dengan
  nilai terdaftar, atau subpath di dalam repo terdaftar (mis. ``.``
  saat cwd berada di dalam repo itu). Path bebas DITOLAK.
- Pendaftaran HANYA lewat CLI lokal manusia (``mufakat repo-register``
  atau ``mufakat-room-runner register``) — TIDAK ADA tool MCP atau
  pesan native messaging yang bisa mendaftarkan repo.
- Path HOME (atau leluhur HOME, mis. ``/``) TIDAK BOLEH didaftarkan.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

__all__ = [
    "registry_path",
    "load_registry",
    "save_registry",
    "register_repo",
    "resolve_registered_repo",
    "list_repos",
    "is_git_repo",
]

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def registry_path() -> Path:
    """Lokasi file registry (env override untuk test)."""
    for env in ("MUFAKAT_RUNNER_REGISTRY", "MUFAKAT_REPO_REGISTRY"):
        override = os.environ.get(env, "").strip()
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

    Hanya dipanggil CLI lokal manusia. Nama hanya
    ``[A-Za-z0-9][A-Za-z0-9._-]*``; path harus folder yang ada dan
    TIDAK BOLEH HOME atau leluhur HOME (audit N3: HOME pernah bisa
    didaftarkan lewat pesan apa pun).
    """
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ValueError(f"Nama repo tidak valid: {name!r}")
    resolved = Path(repo_path).resolve()
    if not resolved.is_dir():
        raise ValueError(f"Repo tidak ditemukan: {repo_path!r}")
    home = Path.home().resolve()
    if resolved == home or resolved in home.parents:
        raise ValueError(
            "Repo tidak boleh HOME atau leluhur HOME "
            f"(ditolak: {resolved}).")
    data = load_registry()
    data["repos"][name] = str(resolved)
    save_registry(data)
    return {"name": name, "path": str(resolved)}


def resolve_registered_repo(repo: str | Path) -> Path | None:
    """Kembalikan root repo terdaftar untuk ``repo``, else None.

    ``repo`` boleh berupa nama terdaftar, path yang persis sama
    dengan nilai terdaftar, atau subpath di dalam repo terdaftar
    (mis. ``"."`` saat cwd di dalam repo itu). Path bebas yang tidak
    terdaftar DITOLAK.
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
            registered = Path(value).resolve()
        except OSError:
            continue
        if resolved == registered or registered in resolved.parents:
            return registered if registered.is_dir() else None
    return None


def list_repos() -> dict[str, str]:
    """Semua repo terdaftar (nama -> path)."""
    return dict(load_registry().get("repos", {}))


def is_git_repo(path: str | Path) -> bool:
    """True bila ``path`` adalah root repo git (punya ``.git``)."""
    try:
        target = Path(path)
    except (TypeError, ValueError):
        return False
    return target.is_dir() and (target / ".git").exists()
