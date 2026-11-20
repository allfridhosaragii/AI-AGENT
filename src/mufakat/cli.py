"""CLI MUFAKAT (T12–T14): run, debate, resume, status, doctor.

Hanya mengimpor Typer/Rich + :mod:`mufakat.runner` (stdlib saja).
Modul berat yang belum ada (mis. graph LangGraph) TIDAK diimpor di sini —
:func:`mufakat.runner.create_run` sudah menanganinya dengan try/except
dan fallback penulisan langsung.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, cast

import typer

try:
    from rich.console import Console
    from rich.table import Table
except Exception:  # pragma: no cover - fallback bila rich belum terpasang
    Console = None  # type: ignore
    Table = None  # type: ignore

if TYPE_CHECKING:
    from rich.table import Table as RichTable

from mufakat.runner import create_run, list_runs, read_run, runs_dir

app = typer.Typer(
    name="mufakat",
    help="MUFAKAT — debat multi-AI menuju mufakat: debat, spesifikasi, kode, audit, test.",
    no_args_is_help=True,
)
console = Console() if Console is not None else None


def _echo(message: str) -> None:
    if console is not None:
        console.print(message)
    else:
        print(message)


def _table(title: str, columns: list[str]) -> RichTable | None:
    if Table is None or console is None:
        return None
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    return cast("RichTable", table)


def _show_table(table: RichTable | None, rows: list[list[str]]) -> None:
    if table is None or console is None:
        for row in rows:
            print(" | ".join(row))
        return
    for row in rows:
        table.add_row(*row)
    console.print(table)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
@app.command("run")
def run_command(
    idea: str = typer.Argument(..., help="Ide / permintaan untuk diproses pipeline."),
    provider: str = typer.Option(
        "mock", "--provider", "-p", help="Provider debat (default: mock)."
    ),
    output: str = typer.Option(
        "runs", "--output", "-o", help="Folder output run (default: runs)."
    ),
) -> None:
    """Jalankan pipeline MUFAKAT (mock bila provider belum terhubung)."""
    result = create_run(idea, provider=provider, output=output, mode="run")
    _echo(f"[green]Run selesai[/green] — run_id: [bold]{result['run_id']}[/bold]")
    _echo(f"Folder: {result['dir']}")
    _echo("Artefak: transcript.jsonl, rounds/round-01.md, spec.md, final_report.md")


@app.command("debate")
def debate_command(
    topic: str = typer.Argument(..., help="Topik debat."),
    provider: str = typer.Option(
        "mock", "--provider", "-p", help="Provider debat (default: mock)."
    ),
    output: str = typer.Option(
        "runs", "--output", "-o", help="Folder output run (default: runs)."
    ),
) -> None:
    """Debat saja (mode debate): hasil akhirnya spec.md."""
    result = create_run(topic, provider=provider, output=output, mode="debate")
    _echo(f"[green]Debat selesai[/green] — run_id: [bold]{result['run_id']}[/bold]")
    _echo(f"Spec: {result['dir']}/spec.md")


@app.command("resume")
def resume_command(
    run_id: str = typer.Argument(..., help="ID run yang akan dilanjutkan."),
    output: str = typer.Option(
        "runs", "--output", "-o", help="Folder runs (default: runs)."
    ),
) -> None:
    """Baca runs/<run_id>/ lalu tulis status lanjutannya."""
    info = read_run(run_id, output)
    if info is None:
        _echo(f"[red]Run tidak ditemukan:[/red] {run_id} (di {runs_dir(output)})")
        raise typer.Exit(code=1)
    run_dir = Path(info["dir"])
    status_path = run_dir / "status.json"
    status = {}
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            status = {}
    from mufakat.runner import utcnow

    status["status"] = "resumed"
    status["resumed_at"] = utcnow()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    _echo(f"[green]Run dilanjutkan[/green] — run_id: [bold]{run_id}[/bold]")
    _echo(f"Status: resumed | pesan transkrip: {info['message_count']} | dir: {info['dir']}")


# ---------------------------------------------------------------------------
# approve — HANYA manusia (audit H1, putaran 2: N8 + GPT 3)
# ---------------------------------------------------------------------------
# --yes DIHAPUS (N8): agen CLI yang punya shell di repo dulu bisa
# menjalankan `mufakat approve <id> --yes` dan menyetujui commit-nya
# sendiri. Satu-satunya jalan non-interaktif adalah env eksplisit
# MUFAKAT_ALLOW_NONINTERACTIVE_APPROVE=1, yang dicatat ke stderr —
# untuk skrip operator manusia, BUKAN untuk agen.
_NONINTERACTIVE_APPROVE_ENV = "MUFAKAT_ALLOW_NONINTERACTIVE_APPROVE"
_MAX_DIFF_CHARS = 20_000


def _git_text(repo: str, *args: str) -> str:
    """Output `git -C <repo> <args>` ('' bila gagal)."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=60, shell=False)
    except Exception:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


@app.command("approve")
def approve_command(
    approval_id: str = typer.Argument(..., help="ID approval yang diputus."),
    repo: str = typer.Option(".", "--repo", help="Repo yang diff-nya diikat."),
    note: str = typer.Option("", "--note", help="Catatan keputusan."),
) -> None:
    """Setujui/tolak approval sebagai MANUSIA (bukan AI/MCP).

    Menampilkan diff LENGKAP (bukan hanya statistik) + hash-nya,
    meminta konfirmasi ``y/N`` di TTY, lalu menerbitkan token sekali
    pakai (24 jam) yang terikat hash diff, repo, branch, dan worktree
    tersebut. Token HANYA ditampilkan sekali di sini — simpan
    baik-baik; ``git_commit`` memakainya satu kali.
    """
    import sys

    from mufakat.mcp_server import approval_store
    from mufakat.mcp_server.domains.approval import decide_approval

    record = approval_store.get_approval(approval_id)
    if record is None:
        _echo(f"[red]Approval tidak ditemukan:[/red] {approval_id}")
        raise typer.Exit(code=1)
    if record["status"] != "pending":
        _echo(f"[red]Approval sudah diputus:[/red] {record['status']}")
        raise typer.Exit(code=1)
    repo_path = str(Path(repo).resolve())
    diff_hash = approval_store.diff_hash_for_repo(repo_path)
    if not diff_hash:
        # N12: hash kosong (bukan repo / git error / tanpa diff) tidak
        # boleh menghasilkan approval — token tanpa ikatan diff akan
        # ditolak juga di verify_token.
        _echo("[red]Tidak ada diff / bukan repo git — approval butuh "
              "hash diff yang tidak kosong.[/red]")
        raise typer.Exit(code=1)
    branch = _git_text(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    worktree = _git_text(repo_path, "rev-parse", "--show-toplevel").strip()
    _echo(f"Approval: [bold]{approval_id}[/bold]")
    _echo(f"Judul: {record.get('title', '')}")
    _echo(f"Run: {record.get('run_id', '') or '-'}")
    _echo(f"Diminta oleh: {record.get('requested_by', '') or '-'}")
    _echo(f"Repo: {repo_path}")
    _echo(f"Branch: {branch or '(tidak diketahui)'}")
    _echo(f"Worktree: {worktree or repo_path}")
    _echo(f"Hash diff saat ini: [bold]{diff_hash}[/bold]")
    # Diff LENGKAP (GPT 3): statistik saja menyembunyikan isi perubahan.
    full_diff = _git_text(repo_path, "diff", "HEAD")
    if full_diff.strip():
        shown = full_diff[:_MAX_DIFF_CHARS]
        _echo("Diff lengkap (dibatasi 20000 karakter):")
        _echo(shown)
        if len(full_diff) > _MAX_DIFF_CHARS:
            _echo(f"... (dipotong, total {len(full_diff)} karakter)")
    noninteractive = os.environ.get(_NONINTERACTIVE_APPROVE_ENV, "") == "1"
    if noninteractive:
        print(
            "[audit] approve non-interaktif diizinkan via "
            f"{_NONINTERACTIVE_APPROVE_ENV}=1 untuk {approval_id} "
            f"(repo {repo_path}, hash {diff_hash})",
            file=sys.stderr,
        )
    else:
        # TTY diperiksa di fd 0 (bukan sys.stdin — runner test
        # mengganti sys.stdin, fd tetap milik proses).
        if not os.isatty(0):
            _echo("[red]Bukan TTY: persetujuan butuh konfirmasi manusia "
                  "di terminal. Non-interaktif hanya lewat env "
                  f"{_NONINTERACTIVE_APPROVE_ENV}=1 (dicatat).[/red]")
            raise typer.Exit(code=1)
        confirmed = typer.confirm("Setujui approval ini?", default=False)
        if not confirmed:
            result = decide_approval(approval_id, False, decided_by="human-cli",
                                     note=note or "ditolak di CLI",
                                     diff_hash=diff_hash, repo_path=repo_path,
                                     branch=branch, worktree=worktree)
            _echo(f"[yellow]Approval ditolak.[/yellow] status: {result.get('status')}")
            raise typer.Exit(code=0)
    result = decide_approval(approval_id, True, decided_by="human-cli",
                             note=note, diff_hash=diff_hash,
                             repo_path=repo_path, branch=branch,
                             worktree=worktree)
    token = result.get("approval_token", "")
    _echo("[green]Approval DISETUJUI.[/green]")
    _echo(f"Hash diff terikat: {diff_hash}")
    _echo("Token sekali pakai (24 jam, HANYA tampil sekali):")
    _echo(f"[bold]{token}[/bold]")
    _echo("Pakai: git_commit(approval_id=..., approval_token=<token>).")


# ---------------------------------------------------------------------------
# repo-register / repo-list — registry repo Git (GPT 5, N3)
# ---------------------------------------------------------------------------
@app.command("repo-register")
def repo_register_command(
    name: str = typer.Argument(..., help="Nama repo (mis. ai-agent)."),
    path: str = typer.Argument(..., help="Path folder repo."),
) -> None:
    """Daftarkan repo Git ke registry (~/.mufakat/runner.json).

    HANYA lewat CLI lokal manusia — operasi Git MCP hanya menerima
    repo terdaftar. HOME / leluhur HOME ditolak; path harus folder
    repo git yang ada.
    """
    from mufakat.mcp_server import repo_registry

    try:
        result = repo_registry.register_repo(name, path)
    except ValueError as exc:
        _echo(f"[red]Gagal mendaftarkan repo:[/red] {exc}")
        raise typer.Exit(code=1)
    if not repo_registry.is_git_repo(result["path"]):
        _echo("[yellow]Peringatan: path terdaftar bukan root repo git "
              "(.git tidak ditemukan) — operasi Git akan gagal sampai "
              "path diperbaiki.[/yellow]")
    _echo(f"[green]Repo terdaftar:[/green] {result['name']} -> {result['path']}")


@app.command("repo-list")
def repo_list_command() -> None:
    """Tampilkan semua repo terdaftar di registry."""
    from mufakat.mcp_server import repo_registry

    repos = repo_registry.list_repos()
    if not repos:
        _echo("Belum ada repo terdaftar. Daftarkan lewat: "
              "mufakat repo-register <nama> <path>")
        return
    for name, path in sorted(repos.items()):
        _echo(f"{name} -> {path}")


@app.command("status")
def status_command(
    run_id: str = typer.Argument(..., help="ID run yang dicek statusnya."),
    output: str = typer.Option(
        "runs", "--output", "-o", help="Folder runs (default: runs)."
    ),
) -> None:
    """Tampilkan tabel status satu run."""
    info = read_run(run_id, output)
    if info is None:
        _echo(f"[red]Run tidak ditemukan:[/red] {run_id} (di {runs_dir(output)})")
        raise typer.Exit(code=1)
    table = _table(f"Status run {run_id}", ["Field", "Nilai"])
    _show_table(
        table,
        [
            ["run_id", str(info["run_id"])],
            ["status", str(info["status"])],
            ["mode", str(info["mode"])],
            ["provider", str(info["provider"])],
            ["ide", str(info["idea"])[:100]],
            ["dibuat", str(info["created_at"])],
            ["pesan transkrip", str(info["message_count"])],
            ["spec.md", "ya" if info["has_spec"] else "tidak"],
            ["final_report.md", "ya" if info["has_final_report"] else "tidak"],
            ["folder", str(info["dir"])],
        ],
    )


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
_BINARIES = [
    "codex",
    "copilot",
    "agy",
    "claude",
    "opencode",
    "docker",
    "semgrep",
    "bandit",
    "gitleaks",
    "trivy",
    "ruff",
]
_API_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "QWEN_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
]


@app.command("doctor")
def doctor_command() -> None:
    """Periksa kesiapan lingkungan: binary, API key (hanya ada/tidak), Docker."""
    table = _table("MUFAKAT doctor — kesiapan lingkungan", ["Pemeriksaan", "Hasil"])
    rows: list[list[str]] = []
    for binary in _BINARIES:
        found = shutil.which(binary)
        rows.append([f"binary: {binary}", "OK" if found else "TIDAK"])
    for key in _API_KEYS:
        # Hanya ada/tidak — NILAI key tidak pernah ditampilkan.
        rows.append([f"env: {key}", "ADA" if os.environ.get(key) else "TIDAK"])
    docker_ok = shutil.which("docker") is not None
    docker_running = False
    if docker_ok:
        try:
            proc = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            docker_running = proc.returncode == 0
        except Exception:
            docker_running = False
    rows.append(["docker daemon", "OK" if docker_running else "TIDAK"])
    rows.append(["runs dir", str(runs_dir())])
    rows.append(["jumlah run", str(len(list_runs()))])
    _show_table(table, rows)
    _echo("Catatan: doctor tidak pernah menampilkan nilai API key.")


def main() -> None:
    """Entry point console script ``mufakat``."""
    app()


if __name__ == "__main__":
    main()
