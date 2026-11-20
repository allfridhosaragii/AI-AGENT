"""Helper aman untuk tool MCP MUFAKAT (diperbaiki audit 20 Nov 2026).

- terminal: allowlist ``echo`` / ``ls`` saja, tanpa shell, tanpa
  metakarakter shell. ``pytest`` DIHAPUS dari allowlist (C1):
  eksekusi test HANYA lewat sandbox Docker (``mufakat.gates``).
- filesystem (audit putaran 2, C3-sisa + GPT 1): root workspace
  EKSPLISIT dari env ``MUFAKAT_WORKSPACE_ROOTS`` (WAJIB — tanpa env,
  baca file DITOLAK); ``cwd`` BUKAN lagi root implisit. Root yang
  sama dengan HOME atau leluhur HOME (``/``, ``/home``) DITOLAK.
  Blocklist diperluas: ``.gnupg``/``.docker``/``.kube``/``.mufakat``/
  ``.mozilla``/``AppData``/``Library``/``.local/share``, nama
  ``.npmrc``/``.pypirc``/``Cookies``/``Login Data``, akhiran
  ``*_history``, dan ``*.db``/``*.sqlite3``. TIDAK ADA parameter
  ``allowed_roots`` di tool MCP — pemanggil AI tidak boleh
  memperluas root (GPT 1: dulu ``filesystem_read(path,
  allowed_roots=["/"])`` menggantikan workspace).
- git: hanya repo yang TERDAFTAR di registry
  (:mod:`mufakat.mcp_server.repo_registry`, file yang sama dengan
  registry Local Runner); argv tetap, tanpa shell.
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
    "workspace_roots",
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
# Folder kredensial / profil yang TIDAK PERNAH boleh dibaca (C3-sisa).
# Berlaku untuk komponen path mana pun, bukan hanya di bawah HOME:
# audit membuktikan ~/.npmrc, ~/.docker/config.json, ~/.gnupg, ~/.kube,
# ~/.mufakat/runner.json, runs/approvals.db, dan Login Data terbaca
# saat cwd == HOME.
BLOCKED_HOME_PATHS = (
    ".ssh", ".config", ".codex", ".claude", ".gemini", ".aws",
    ".gnupg", ".docker", ".kube", ".mufakat", ".mozilla",
    "AppData", "Library",
)
# Pasangan komponen yang diblokir (mis. ~/.local/share).
BLOCKED_PATH_PAIRS = ((".local", "share"),)
# Nama file/folder yang diblokir di mana pun (cocok persis, tanpa case).
BLOCKED_FILE_NAMES = (".npmrc", ".pypirc", ".git-credentials",
                      "cookies", "login data")
# Akhiran nama file yang diblokir (mis. .bash_history, data.db).
BLOCKED_NAME_SUFFIXES = ("_history", ".db", ".sqlite", ".sqlite3")

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


def workspace_roots() -> list[Path]:
    """Root workspace eksplisit dari env ``MUFAKAT_WORKSPACE_ROOTS``.

    Env WAJIB (pathsep-separated). Root yang sama dengan HOME atau
    leluhur HOME (``/``, ``/home``) DITOLAK dan tidak masuk daftar —
    audit C3-sisa: server MCP sering jalan dengan cwd = HOME sehingga
    seluruh kredensial home terbaca. ``cwd`` TIDAK PERNAH menjadi
    root implisit lagi. Daftar kosong = belum dikonfigurasi.
    """
    roots: list[Path] = []
    home = Path.home().resolve()
    extra = os.environ.get("MUFAKAT_WORKSPACE_ROOTS", "")
    for part in extra.split(os.pathsep):
        if not part.strip():
            continue
        try:
            resolved = Path(part).resolve()
        except OSError:
            continue
        if resolved == home or resolved in home.parents:
            # Root == HOME atau leluhur HOME: tolak (C3-sisa).
            continue
        roots.append(resolved)
    return roots


def _default_allowed_roots() -> list[Path]:
    """Alias lama: root workspace eksplisit (lihat :func:`workspace_roots`)."""
    return workspace_roots()


def _is_blocked_home_path(resolved: Path) -> bool:
    """True bila path menyentuh folder/file kredensial (C3-sisa).

    Komponen yang diblokir (``.gnupg``, ``.docker``, ``.kube``,
    ``.mufakat``, ``.mozilla``, ``AppData``, ``Library``, plus yang
    lama) berlaku di mana pun di path; pasangan ``.local/share``
    diblokir; nama ``.npmrc``/``.pypirc``/``Cookies``/``Login Data``
    dan akhiran ``*_history``/``*.db``/``*.sqlite3`` diblokir.
    """
    parts = [p.lower() for p in resolved.parts]
    blocked_dirs = {p.lower() for p in BLOCKED_HOME_PATHS}
    if any(part in blocked_dirs for part in parts):
        return True
    for first, second in BLOCKED_PATH_PAIRS:
        if any(parts[i] == first and i + 1 < len(parts)
               and parts[i + 1] == second for i in range(len(parts))):
            return True
    name = resolved.name.lower()
    if name in BLOCKED_FILE_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in BLOCKED_NAME_SUFFIXES)


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


def read_file_safe(path: str) -> dict:
    """Baca file teks bila aman: di dalam root workspace eksplisit
    (env ``MUFAKAT_WORKSPACE_ROOTS``, wajib), bukan symlink, bukan
    kredensial, ada, dan < 1 MB.

    TIDAK ADA parameter ``allowed_roots``: root hanya dari konfigurasi
    internal server — pemanggil MCP tidak boleh memperluasnya
    (GPT 1). Tanpa env, baca DITOLAK (fail-closed).
    """
    target = Path(path)
    if _passes_through_symlink(target):
        return err("Path melewati symlink — ditolak.", path=str(target))
    try:
        resolved = target.resolve()
    except OSError as exc:
        return err(f"Path tidak valid: {exc}", path=str(target))
    if _is_blocked_home_path(resolved):
        return err("Folder/file kredensial tidak boleh dibaca lewat tool ini.",
                   path=str(target))
    roots = workspace_roots()
    if not roots:
        return err(
            "MUFAKAT_WORKSPACE_ROOTS belum dikonfigurasi — baca file "
            "ditolak. Set env ke folder workspace eksplisit (bukan HOME).",
            path=str(target))
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
    """Status git read-only (argv tetap, tanpa shell).

    Repo HARUS terdaftar di registry (:mod:`repo_registry`, GPT 5):
    nama terdaftar, path terdaftar, atau subpath di dalamnya.
    """
    from mufakat.mcp_server.repo_registry import resolve_registered_repo

    registered = resolve_registered_repo(repo_path)
    if registered is None:
        return err(
            "Repo belum terdaftar di registry (~/.mufakat/runner.json). "
            "Daftarkan dulu lewat CLI lokal: "
            "`mufakat repo-register <nama> <path>`.",
            repo_path=repo_path)
    target = registered
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
        repo_path=str(target),
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
