"""Authorization layer umum untuk tool MCP (audit putaran 2: GPT 5).

Sebelumnya permission (``read`` / ``write-sandbox`` /
``approval-required`` / ``execute-approved``) hanya metadata di
``CONTRACTS`` tiap domain; ``register_all()`` mendaftarkan fungsi
langsung ke FastMCP tanpa otorisasi apa pun. Modul ini menegakkan
permission SEBELUM tool dijalankan:

- Setiap tool yang didaftarkan lewat :func:`register_all` dibungkus
  :func:`authorize` — wrapper memeriksa permission dari kontrak
  (satu sumber kebenaran: ``CONTRACTS`` semua domain) lalu
  memanggil fungsi aslinya hanya bila lolos.
- ``read`` / ``propose``: argumen path tidak boleh menyentuh
  folder/file kredensial (blocklist C3-sisa).
- ``write-sandbox``: semua argumen path harus berada di bawah
  ``runs/`` atau root workspace eksplisit (``MUFAKAT_WORKSPACE_ROOTS``).
- ``approval-required``: wajib ada ``approval_id`` + ``approval_token``
  non-kosong SEBELUM tool jalan (verifikasi token tetap di tool).
- ``execute-approved``: eksekusi hanya terhadap target di workspace
  / repo terdaftar / ``runs/``; ``terminal_run`` diperiksa allowlist
  perintahnya di sini, sebelum tool jalan.

Tool yang tidak dikenal di kontrak DITOLAK (fail-closed). Wrapper
memakai ``functools.wraps`` sehingga signature/annotasi yang dilihat
FastMCP tidak berubah.
"""

from __future__ import annotations

import functools
import inspect
from pathlib import Path

from mufakat.mcp_server.tools import (
    ALLOWED_TERMINAL_COMMANDS,
    SHELL_META,
    _is_blocked_home_path,
    err,
    workspace_roots,
)
from mufakat.runner import runs_dir

__all__ = [
    "PATH_ARG_NAMES",
    "permission_for",
    "check_permission",
    "authorize",
    "register_tool",
]

# Nama argumen yang diperlakukan sebagai path di semua tool.
PATH_ARG_NAMES = ("path", "repo_path", "spec_path", "worktree_path",
                  "target", "worktree")

_CONTRACTS_CACHE: dict[str, dict] | None = None


def _contracts() -> dict[str, dict]:
    """Peta nama tool -> kontrak (nama, permission, scope, domain)."""
    global _CONTRACTS_CACHE  # noqa: PLW0603 - cache modul sekali isi
    if _CONTRACTS_CACHE is None:
        from mufakat.mcp_server.domains import contracts

        _CONTRACTS_CACHE = {c["name"]: c for c in contracts()}
    return _CONTRACTS_CACHE


def permission_for(tool_name: str) -> str | None:
    """Permission kontrak untuk ``tool_name``; None bila tidak dikenal."""
    contract = _contracts().get(tool_name)
    return contract["permission"] if contract else None


def _path_args(args: dict) -> list[tuple[str, str]]:
    """Argumen path (string non-kosong) dari pemanggilan tool."""
    out = []
    for name in PATH_ARG_NAMES:
        value = args.get(name)
        if isinstance(value, str) and value.strip():
            out.append((name, value))
    return out


def _is_under(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return any(resolved == root or root in resolved.parents for root in roots)


def _blocked_path_error(args: dict) -> str | None:
    """Error bila ada argumen path yang menyentuh kredensial; else None."""
    for name, value in _path_args(args):
        try:
            resolved = Path(value).resolve()
        except OSError:
            continue
        if _is_blocked_home_path(resolved):
            return (f"Argumen {name} menyentuh folder/file kredensial "
                    f"yang diblokir: {value}")
    return None


def _sandbox_error(args: dict) -> str | None:
    """Error bila argumen path keluar dari runs/ atau workspace; else None."""
    roots = [runs_dir().resolve(), *workspace_roots()]
    for name, value in _path_args(args):
        if not _is_under(Path(value), roots):
            return (f"Argumen {name} di luar sandbox (runs/ atau workspace "
                    f"yang diizinkan): {value}")
    return None


def _registered_repo_error(args: dict) -> str | None:
    """Error bila repo_path bukan repo terdaftar; else None."""
    repo_path = args.get("repo_path")
    if not isinstance(repo_path, str) or not repo_path.strip():
        return None
    from mufakat.mcp_server.repo_registry import resolve_registered_repo

    if resolve_registered_repo(repo_path) is None:
        return (f"Repo belum terdaftar di registry "
                f"(mufakat repo-register <nama> <path>): {repo_path}")
    return None


def check_permission(tool_name: str, permission: str | None,
                     args: dict) -> str | None:
    """Periksa otorisasi SEBELUM tool dijalankan.

    Kembalikan pesan error bila ditolak, else None (diizinkan).
    """
    if permission is None:
        return (f"Tool tidak dikenal di kontrak MCP — ditolak "
                f"(fail-closed): {tool_name}")
    if permission not in ("read", "propose", "write-sandbox",
                          "approval-required", "execute-approved"):
        return f"Permission tidak dikenal — ditolak: {permission}"
    if permission in ("read", "propose"):
        return _blocked_path_error(args)
    if permission == "write-sandbox":
        blocked = _blocked_path_error(args)
        if blocked:
            return blocked
        repo_err = _registered_repo_error(args)
        if repo_err:
            return repo_err
        return _sandbox_error(args)
    if permission == "approval-required":
        if not args.get("approval_id") or not args.get("approval_token"):
            return ("Tool ini butuh approval manusia: approval_id + "
                    "approval_token sekali pakai wajib diisi "
                    "(minta lewat approval_request, setujui lewat "
                    "`mufakat approve <id>`).")
        return _registered_repo_error(args)
    # execute-approved: eksekusi hanya di dalam sandbox/workspace/repo
    # terdaftar; terminal_run diperiksa allowlist-nya di sini.
    if tool_name == "terminal_run":
        command = args.get("command", "")
        if not isinstance(command, str) or not command.strip():
            return "Perintah kosong."
        if any(ch in command for ch in SHELL_META):
            return "Perintah mengandung metakarakter shell — ditolak."
        first = command.strip().split(None, 1)[0]
        if first not in ALLOWED_TERMINAL_COMMANDS:
            return ("Perintah ditolak: hanya echo dan ls yang diizinkan "
                    f"(diterima: {first}).")
        return None
    blocked = _blocked_path_error(args)
    if blocked:
        return blocked
    repo_err = _registered_repo_error(args)
    if repo_err:
        return repo_err
    return _sandbox_error(args)


def authorize(fn, permission: str | None):
    """Bungkus tool MCP dengan pemeriksaan permission pra-eksekusi."""
    tool_name = fn.__name__

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        bound = {}
        try:
            sig = inspect.signature(fn)
            bound = dict(sig.bind_partial(*args, **kwargs).arguments)
        except (TypeError, ValueError):
            bound = dict(kwargs)
            for name, value in zip(inspect.signature(fn).parameters, args):
                bound[name] = value
        denied = check_permission(tool_name, permission, bound)
        if denied is not None:
            return err(denied, tool=tool_name, permission=permission or "",
                       authorized=False)
        return fn(*args, **kwargs)

    return wrapper


def register_tool(mcp, fn, permission: str | None = None):
    """Daftarkan satu tool ke FastMCP dengan wrapper otorisasi."""
    if permission is None:
        permission = permission_for(fn.__name__)
    mcp.tool(authorize(fn, permission))
    return fn.__name__
