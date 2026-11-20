"""Helper aman untuk tool MCP MUFAKAT (diperbaiki audit 20 Nov 2026).

- terminal: allowlist ``echo`` / ``ls`` saja, tanpa shell, tanpa
  metakarakter shell. ``pytest`` DIHAPUS dari allowlist (C1):
  eksekusi test HANYA lewat sandbox Docker (``mufakat.gates``).
- filesystem: ALLOWLIST folder (C3) — hanya path yang ``resolve()``-nya
  berada di bawah root workspace (cwd / ``runs/`` / env
  ``MUFAKAT_WORKSPACE_ROOTS``). Symlink ditolak, folder kredensial
  (``~/.ssh``, ``~/.config``, ``~/.codex``, ``~/.claude``,
  ``~/.gemini``, ``~/.aws``, ``~/.git-credentials``) dan ``*.sqlite``
  diblokir eksplisit. Blocklist nama file lama hanya pertahanan
  kedua, bukan mekanisme utama.
- git: hanya argv tetap ``git status``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from mufakat.runner import create_run, new_run_id, read_run, runs_dir

__all__ = [
    "ALLOWED_TERMINAL_COMMANDS",
    "SHELL_META",
    "SECRET_NAME_PATTERNS",
    "BLOCKED_HOME_PATHS",
    "ok",
    "err",
    "run_terminal_command",
    "read_file_safe",
    "git_status_safe",
    "list_agents",
    "create_run_for_mcp",
    "gate_report_for_run",
]

ALLOWED_TERMINAL_COMMANDS = {"echo", "ls"}
# M1: karakter newline/carriage-return ASLI ("\n", "\r") — dulu
# tertulis "\\n\\r" sehingga yang diblokir justru huruf n, r, dan "\".
SHELL_META = set(";|&`$()<>\n\r")
SECRET_NAME_PATTERNS = (".env", "secret", "credentials", ".pem", ".key", "id_rsa", ".netrc")
# Folder/file kredensial yang TIDAK PERNAH boleh dibaca (C3).
BLOCKED_HOME_PATHS = (
    ".ssh", ".config", ".codex", ".claude", ".gemini", ".aws",
)

MAX_READ_BYTES = 1_000_000
MAX_OUTPUT_CHARS = 20_000


def ok(**fields: object) -> dict:
    """Hasil tool sukses: selalu ada kunci ``ok``."""
    result: dict = {"ok": True}
    result.update(fields)
    return result


def err(message: str, **fields: object) -> dict:
    """Hasil tool gagal (aman): alasan + ``ok: False``."""
    result: dict = {"ok": False, "error": message}
    result.update(fields)
    return result


def run_terminal_command(command: str) -> dict:
    """Jalankan perintah HANYA bila masuk allowlist (echo/ls).

    Tanpa shell, tanpa metakarakter, tanpa perintah lain. ``pytest``
    TIDAK diizinkan di sini — jalankan test lewat gate sandbox.
    """
    if not command or not command.strip():
        return err("Perintah kosong.")
    if any(ch in command for ch in SHELL_META):
        return err("Perintah mengandung metakarakter shell — ditolak.")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        return err(f"Perintah tidak bisa diparse: {exc}")
    if not parts or parts[0] not in ALLOWED_TERMINAL_COMMANDS:
        return err(
            "Perintah ditolak: hanya echo dan ls yang diizinkan. "
            "pytest hanya boleh lewat gate sandbox.",
            allowed=sorted(ALLOWED_TERMINAL_COMMANDS),
            received=parts[0] if parts else "",
        )
    try:
        proc = subprocess.run(
            parts, capture_output=True, text=True, timeout=120, shell=False
        )
    except subprocess.TimeoutExpired:
        return err("Perintah kehabisan waktu (timeout 120 detik).", command=parts[0])
    except Exception as exc:  # noqa: BLE001 — laporkan sebagai dict, bukan crash
        return err(f"Gagal menjalankan perintah: {exc}", command=parts[0])
    return ok(
        command=parts[0],
        returncode=proc.returncode,
        stdout=proc.stdout[:MAX_OUTPUT_CHARS],
        stderr=proc.stderr[:MAX_OUTPUT_CHARS],
    )


def _default_allowed_roots() -> list[Path]:
    """Root yang boleh dibaca: cwd, runs/, dan env MUFAKAT_WORKSPACE_ROOTS."""
    roots = [Path.cwd().resolve(), runs_dir().resolve()]
    extra = os.environ.get("MUFAKAT_WORKSPACE_ROOTS", "")
    for part in extra.split(os.pathsep):
        if part.strip():
            try:
                roots.append(Path(part).resolve())
            except OSError:
                continue
    return roots


def _is_blocked_home_path(resolved: Path) -> bool:
    """True bila path di bawah folder kredensial home / file sensitif."""
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
    except ValueError:
        return False
    if rel.parts and rel.parts[0] in BLOCKED_HOME_PATHS:
        return True
    if resolved.name == ".git-credentials":
        return True
    return False


def _passes_through_symlink(target: Path) -> bool:
    """True bila target atau komponen induknya yang ada adalah symlink."""
    current = target if target.is_absolute() else Path.cwd() / target
    if current.is_symlink():
        return True
    for parent in current.parents:
        if parent.is_symlink():
            return True
        if parent == Path(parent.anchor):
            break
    return False


def _is_secret_path(path: Path) -> bool:
    name = path.name.lower()
    return any(pat in name for pat in SECRET_NAME_PATTERNS)


def read_file_safe(path: str, allowed_roots=None) -> dict:
    """Baca file teks bila aman: di dalam allowlist root, bukan symlink,
    bukan kredensial, ada, dan < 1 MB."""
    target = Path(path)
    if _passes_through_symlink(target):
        return err("Path melewati symlink — ditolak.", path=str(target))
    try:
        resolved = target.resolve()
    except OSError as exc:
        return err(f"Path tidak valid: {exc}", path=str(target))
    if resolved.suffix.lower() == ".sqlite":
        return err("File SQLite tidak boleh dibaca lewat tool ini.", path=str(target))
    if _is_blocked_home_path(resolved):
        return err("Folder kredensial tidak boleh dibaca lewat tool ini.",
                   path=str(target))
    roots = [Path(r).resolve() for r in allowed_roots] if allowed_roots \
        else _default_allowed_roots()
    if not any(resolved == root or root in resolved.parents for root in roots):
        return err("File di luar workspace yang diizinkan — ditolak.",
                   path=str(target))
    if _is_secret_path(resolved):
        return err("File rahasia tidak boleh dibaca lewat tool ini.", path=resolved.name)
    if not resolved.is_file():
        return err("File tidak ditemukan.", path=str(target))
    try:
        if resolved.stat().st_size > MAX_READ_BYTES:
            return err("File terlalu besar (> 1 MB).", path=str(target))
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return err(f"File tidak bisa dibaca: {exc}", path=str(target))
    return ok(path=str(resolved), size=len(content), content=content[:MAX_OUTPUT_CHARS])


def git_status_safe(repo_path: str = ".") -> dict:
    """Status git read-only (argv tetap, tanpa shell)."""
    target = Path(repo_path)
    if not target.is_dir():
        return err("Folder repo tidak ditemukan.", repo_path=repo_path)
    try:
        proc = subprocess.run(
            ["git", "-C", str(target), "status", "--porcelain=v1", "--branch"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except Exception as exc:  # noqa: BLE001
        return err(f"git gagal dijalankan: {exc}", repo_path=repo_path)
    if proc.returncode != 0:
        return err(
            "Bukan repositori git atau git error.",
            repo_path=repo_path,
            stderr=proc.stderr[:2000],
        )
    lines = [line for line in proc.stdout.splitlines() if line]
    branch = next((line[3:] for line in lines if line.startswith("## ")), "")
    return ok(
        repo_path=repo_path,
        branch=branch,
        changes=lines[1:] if branch else lines,
        dirty=len(lines) > 1,
    )


def list_agents() -> dict:
    """Daftar definisi agen (mock — dari provider_registry bila tersedia)."""
    agents: list[dict] = []
    try:
        from mufakat.provider_registry import default_registry

        for provider in default_registry().list_all():
            agents.append({"agent_id": provider.name,
                           "provider": provider.name,
                           "capabilities": provider.capabilities})
    except Exception:
        pass
    if not agents:
        agents = [
            {"agent_id": "researcher", "role": "researcher", "provider": "mock"},
            {"agent_id": "debater-pro", "role": "debater", "provider": "mock"},
            {"agent_id": "debater-contra", "role": "debater", "provider": "mock"},
            {"agent_id": "moderator", "role": "moderator", "provider": "mock"},
            {"agent_id": "coder", "role": "coder", "provider": "mock"},
            {"agent_id": "reviewer", "role": "reviewer", "provider": "mock"},
            {"agent_id": "auditor", "role": "auditor", "provider": "mock"},
            {"agent_id": "tester", "role": "tester", "provider": "mock"},
        ]
    return ok(agents=agents, count=len(agents))


def create_run_for_mcp(idea: str, provider: str = "mock", mode: str = "run") -> dict:
    """Buat run lewat runner bersama (dipakai CLI, MCP, dan Web)."""
    return create_run(idea, provider=provider, mode=mode)


def gate_report_for_run(run_id: str) -> dict:
    """Laporan gate: baca runs/<id>/gates bila ada, else belum terverifikasi."""
    try:
        from mufakat.sandbox.worktree import validate_run_id

        validate_run_id(run_id)
    except ValueError:
        return err("run_id tidak valid.", run_id=run_id, verified=False)
    info = read_run(run_id)
    if info is None:
        return err("Run tidak ditemukan.", run_id=run_id, verified=False)
    gates_dir = runs_dir() / run_id / "gates"
    gate_files: list[dict] = []
    if gates_dir.is_dir():
        for child in sorted(gates_dir.iterdir()):
            if child.is_file():
                entry: dict = {"name": child.name, "path": str(child)}
                if child.suffix in {".json", ".sarif"}:
                    try:
                        entry["data"] = json.loads(child.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        entry["data"] = None
                gate_files.append(entry)
    verified = bool(gate_files)
    return ok(
        run_id=run_id,
        verified=verified,
        status="terverifikasi" if verified else "belum terverifikasi",
        gates=gate_files,
        note=(
            "Gate terverifikasi bila ada hasil di runs/<run_id>/gates/."
            if not verified
            else "Ada hasil gate — periksa tiap file untuk detail lolos/gagal."
        ),
    )


def new_id(prefix: str) -> str:
    """ID pendek berprefix untuk meeting/task/project/approval."""
    return f"{prefix}-{new_run_id()}"


def env_presence(names: list[str]) -> dict[str, bool]:
    """Ada/tidak-nya env var — tanpa pernah mengembalikan nilainya."""
    return {name: bool(os.environ.get(name)) for name in names}


def which_binaries(names: list[str]) -> dict[str, bool]:
    """Ada/tidak-nya binary di PATH."""
    return {name: shutil.which(name) is not None for name in names}
