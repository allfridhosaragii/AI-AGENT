"""Helper aman untuk tool MCP MUFAKAT.

Semua tool mengembalikan dict (bukan mengeksekusi hal berbahaya):
- terminal: allowlist ``echo`` / ``ls`` / ``pytest`` saja, tanpa shell,
  tanpa metakarakter shell.
- filesystem: menolak file rahasia (.env, *secret*, *.pem, *.key, dsb.)
  dan membatasi ukuran baca.
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
    "ok",
    "err",
    "run_terminal_command",
    "read_file_safe",
    "git_status_safe",
    "list_agents",
    "create_run_for_mcp",
    "gate_report_for_run",
]

ALLOWED_TERMINAL_COMMANDS = {"echo", "ls", "pytest"}
SHELL_META = set(";|&`$()<>\\n\\r")
SECRET_NAME_PATTERNS = (".env", "secret", "credentials", ".pem", ".key", "id_rsa", ".netrc")

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
    """Jalankan perintah HANYA bila masuk allowlist (echo/ls/pytest).

    Tanpa shell, tanpa metakarakter, tanpa perintah lain.
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
            "Perintah ditolak: hanya echo, ls, dan pytest yang diizinkan.",
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


def _is_secret_path(path: Path) -> bool:
    name = path.name.lower()
    return any(pat in name for pat in SECRET_NAME_PATTERNS)


def read_file_safe(path: str) -> dict:
    """Baca file teks bila aman: bukan rahasia, ada, dan < 1 MB."""
    target = Path(path)
    if _is_secret_path(target):
        return err("File rahasia tidak boleh dibaca lewat tool ini.", path=target.name)
    if not target.is_file():
        return err("File tidak ditemukan.", path=str(target))
    try:
        if target.stat().st_size > MAX_READ_BYTES:
            return err("File terlalu besar (> 1 MB).", path=str(target))
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return err(f"File tidak bisa dibaca: {exc}", path=str(target))
    return ok(path=str(target), size=len(content), content=content[:MAX_OUTPUT_CHARS])


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
