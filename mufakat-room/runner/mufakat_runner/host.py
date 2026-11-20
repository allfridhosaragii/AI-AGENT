"""Local Runner MUFAKAT Room — Native Messaging host (Claude §5, §T11).

Protokol: stdin/stdout length-prefixed JSON (Chrome Native Messaging):
4 byte little-endian panjang + payload JSON UTF-8.

Perintah yang diterima (JSON) — audit C2: semua perintah memakai
``run_id``, BUKAN path bebas::

    {"command": "init_workspace", "repo": "repo-saya", "run_id": "..."}
    {"command": "apply_files", "run_id": "...", "files": [{"path", "mode", "content"}]}
    {"command": "run_gates", "run_id": "...", "profile": "python|node"}
    {"command": "diff", "run_id": "..."}
    {"command": "request_approval", "run_id": "..."}
    {"command": "confirm_approval", "run_id": "...",
     "approval_id": "...", "code": "123456"}
    {"command": "issue_approval_token", "run_id": "...", "diff_hash": "..."}
    {"command": "commit", "run_id": "...", "message": "...", "approval_token": "..."}
    {"command": "cleanup", "run_id": "..."}
    {"command": "status"}

``register_repo`` TIDAK ADA lagi di kanal ini (audit putaran 2, N3):
repo hanya didaftarkan lewat CLI lokal manusia
``mufakat-room-runner register <nama> <path>``.

Keamanan:
- Repo HANYA dari registry pengguna ``~/.mufakat/runner.json``
  (lihat :mod:`mufakat_runner.registry`); pesan tidak boleh membawa
  path repo/worktree bebas.
- ``cleanup`` hanya menghapus di bawah ``<repo>/runs/<run_id>/wt``.
- ``commit`` HANYA jalan bila ``approval_token`` cocok dengan token
  yang diterbitkan lewat ``issue_approval_token`` — dan token itu
  HANYA terbit setelah persetujuan MANUSIA DI LUAR kanal ekstensi
  (N3/GPT 3): ``request_approval`` menampilkan kode 6 digit lewat
  dialog OS host (zenity/osascript/MessageBox) atau terminal host,
  manusia mengetik kode itu di side panel (``confirm_approval``),
  baru ``issue_approval_token`` menerbitkan token sekali pakai yang
  terikat hash diff + branch + worktree. Pemanggil yang sama TIDAK
  BISA menerbitkan token sendiri: kode tidak pernah dikirim lewat
  kanal ekstensi.
- ``apply_files`` menolak path traversal (``..``, absolut) — lihat
  :mod:`mufakat_runner.worktree`.
- Runner hanya menerima perintah dari ID ekstensi yang terdaftar
  (``allowed_origins`` di manifest host, lihat ``install_host.py``).
  Host TIDAK membuka port jaringan apa pun.
- Tidak ada auto-send / otomasi situs AI di sini: runner hanya mengurus
  worktree + gates lokal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from mufakat_runner import gates as gates_mod
from mufakat_runner import registry as registry_mod
from mufakat_runner import sandbox as sandbox_mod
from mufakat_runner import verdict as verdict_mod
from mufakat_runner import worktree as worktree_mod

__all__ = ["encode_message", "decode_message", "handle_command", "serve", "main"]

# Batas ukuran satu pesan native messaging (Chrome membatasi ~64 MB;
# 16 MB sudah jauh di atas kebutuhan perintah worktree/gates dan
# mencegah host membaca alokasi raksasa dari header yang dibuat-buat).
MAX_MESSAGE_BYTES = 16 * 1024 * 1024

# Kode konfirmasi manusia 6 digit berlaku 10 menit.
APPROVAL_CODE_TTL_MINUTES = 10
APPROVAL_CODE_LENGTH = 6


def _show_human_code(title: str, body: str) -> str:
    """Tampilkan kode konfirmasi ke MANUSIA di luar kanal ekstensi.

    Urutan: dialog OS (zenity di Linux, osascript di macOS,
    MessageBox PowerShell di Windows) -> notifikasi terminal host.
    Kembalikan ``"dialog"`` bila dialog OS tampil, else ``"terminal"``.
    Env ``MUFAKAT_RUNNER_NO_DIALOG=1`` memaksa jalur terminal (server
    tanpa GUI / test). Kode TIDAK PERNAH dikirim lewat pesan native
    messaging — hanya manusia di depan mesin ini yang melihatnya.
    """
    if os.environ.get("MUFAKAT_RUNNER_NO_DIALOG", "") != "1":
        if shutil.which("zenity"):
            try:
                proc = subprocess.run(
                    ["zenity", "--info", f"--title={title}", f"--text={body}",
                     "--width=420"],
                    capture_output=True, timeout=120)
                if proc.returncode == 0:
                    return "dialog"
            except (OSError, subprocess.SubprocessError):
                pass
        if sys.platform == "darwin" and shutil.which("osascript"):
            script = (f'display dialog "{body}" with title "{title}" '
                      'buttons {"OK"} default button "OK"')
            try:
                proc = subprocess.run(["osascript", "-e", script],
                                      capture_output=True, timeout=120)
                if proc.returncode == 0:
                    return "dialog"
            except (OSError, subprocess.SubprocessError):
                pass
        if sys.platform.startswith("win"):
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                f"[System.Windows.Forms.MessageBox]::Show('{body}', '{title}')"
            )
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps],
                    capture_output=True, timeout=120)
                if proc.returncode == 0:
                    return "dialog"
            except (OSError, subprocess.SubprocessError):
                pass
    print(f"[MUFAKAT RUNNER] {title}\n{body}", file=sys.stderr, flush=True)
    return "terminal"


def _git_branch(worktree: str) -> str:
    """Branch worktree ('' bila gagal dibaca)."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=worktree, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _diff_stat(worktree: str) -> str:
    """Ringkasan `git diff HEAD --stat` worktree ('' bila gagal)."""
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD", "--stat"], cwd=worktree,
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def encode_message(payload: dict) -> bytes:
    """Encode satu pesan native messaging (length-prefixed)."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(data)) + data


def decode_message(buffer: bytes) -> tuple[dict, bytes]:
    """Decode satu pesan dari awal ``buffer``; kembalikan (pesan, sisa).

    Melempar ``ValueError`` bila buffer belum berisi satu pesan lengkap
    atau panjang pesan melebihi :data:`MAX_MESSAGE_BYTES`.
    """
    if len(buffer) < 4:
        raise ValueError("Buffer belum berisi header panjang pesan.")
    (length,) = struct.unpack("<I", buffer[:4])
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(
            f"Panjang pesan {length} melebihi batas {MAX_MESSAGE_BYTES} byte."
        )
    if len(buffer) < 4 + length:
        raise ValueError("Buffer belum berisi satu pesan lengkap.")
    payload = json.loads(buffer[4:4 + length].decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Payload native messaging harus object JSON.")
    return payload, buffer[4 + length:]


class RunnerHost:
    """Host native messaging: dispatch perintah + token approval sekali pakai."""

    def __init__(self, approval_token: str | None = None) -> None:
        self.approval_token = approval_token
        self._approval_used = False
        # Token yang diterbitkan lewat issue_approval_token + hash diff
        # yang diikatnya (H6). None = belum ada token terbit.
        self._issued_token: str | None = None
        self._issued_diff_hash: str | None = None
        self._issued_branch: str | None = None
        # Persetujuan manusia yang menunggu kode 6 digit (N3/GPT 3):
        # approval_id -> {run_id, repo, worktree, branch, diff_hash,
        # code_hash, expires_at, confirmed}. Hanya hidup di memori
        # proses host ini; kode TIDAK PERNAH dikirim lewat kanal
        # ekstensi (hanya hash-nya yang disimpan).
        self._pending_approvals: dict[str, dict] = {}

    # -- dispatch --------------------------------------------------------
    def handle_command(self, message: dict) -> dict:
        if not isinstance(message, dict):
            return {"ok": False, "error": "Perintah harus object JSON."}
        command = message.get("command")
        handler = {
            "init_workspace": self._init_workspace,
            "apply_files": self._apply_files,
            "run_gates": self._run_gates,
            "diff": self._diff,
            "request_approval": self._request_approval,
            "confirm_approval": self._confirm_approval,
            "issue_approval_token": self._issue_approval_token,
            "commit": self._commit,
            "cleanup": self._cleanup,
            "status": self._status,
        }.get(command)
        if handler is None:
            if command == "register_repo":
                return {"ok": False,
                        "error": "register_repo TIDAK tersedia lewat native "
                                 "messaging (audit N3). Daftarkan repo lewat "
                                 "CLI lokal: mufakat-room-runner register "
                                 "<nama> <path>."}
            return {"ok": False, "error": f"Perintah tidak dikenal: {command!r}"}
        try:
            return handler(message)
        except Exception as exc:  # noqa: BLE001 - host tidak boleh mati
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def _require_str(message: dict, key: str, default: str = "") -> str:
        value = message.get(key, default)
        if not isinstance(value, str):
            raise ValueError(f"Field {key!r} harus string.")
        return value

    def _resolve_worktree(self, message: dict) -> tuple[str, dict]:
        """Worktree + catatan registry untuk ``run_id``; tolak bila tak dikenal."""
        run_id = self._require_str(message, "run_id", "")
        if not run_id:
            raise ValueError("Field 'run_id' wajib diisi.")
        record = registry_mod.resolve_run(run_id)
        if record is None:
            raise ValueError(
                f"run_id tidak dikenal: {run_id!r} "
                "(buat dulu lewat init_workspace).")
        return record["worktree"], record

    # -- perintah ---------------------------------------------------------
    def _init_workspace(self, message: dict) -> dict:
        repo_arg = message.get("repo", message.get("repo_path", "."))
        if not isinstance(repo_arg, str):
            raise ValueError("Field 'repo' harus string.")
        repo_path = registry_mod.resolve_repo(repo_arg)
        if repo_path is None:
            return {"ok": False,
                    "error": f"Repo belum terdaftar di ~/.mufakat/runner.json: {repo_arg!r}. "
                             "Daftarkan dulu lewat CLI lokal: "
                             "mufakat-room-runner register <nama> <path>."}
        run_id = self._require_str(message, "run_id", "room")
        path = worktree_mod.init_workspace(str(repo_path), run_id)
        # Nama repo untuk catatan: nama terdaftar bila argumen berupa nama.
        data = registry_mod.load_registry()
        repo_name = next((n for n, p in data.get("repos", {}).items()
                          if str(repo_path) == p), str(repo_path))
        registry_mod.record_run(run_id, repo_name, str(path))
        return {"ok": True, "run_id": run_id, "repo": repo_name,
                "worktree": str(path)}

    def _apply_files(self, message: dict) -> dict:
        files = message.get("files") or []
        if not isinstance(files, list):
            raise ValueError("Field 'files' harus list.")
        worktree, _record = self._resolve_worktree(message)
        applied = worktree_mod.apply_files(worktree, files)
        return {"ok": True, "applied": applied}

    def _run_gates(self, message: dict) -> dict:
        worktree, _record = self._resolve_worktree(message)
        profile = message.get("profile", "python")
        if not isinstance(profile, str):
            raise ValueError("Field 'profile' harus string.")
        results = gates_mod.run_gates(worktree, profile=profile)
        verdict_result = verdict_mod.apply_verdict(results)
        return {"ok": True, "results": results, "verdict": verdict_result}

    def _diff(self, message: dict) -> dict:
        worktree, _record = self._resolve_worktree(message)
        return {
            "ok": True,
            "diff": worktree_mod.diff(worktree),
            "diff_hash": worktree_mod.diff_hash(worktree),
        }

    def _request_approval(self, message: dict) -> dict:
        """Minta persetujuan manusia — langkah 1 dari 3 (N3/GPT 3).

        Menghitung diff + hash + branch worktree, membuat kode 6 digit,
        menampilkannya ke manusia DI LUAR kanal ekstensi (dialog OS /
        terminal host), dan menyimpan HANYA hash kode (10 menit).
        KODE TIDAK PERNAH dikembalikan dalam respons — manusia
        membacanya dari dialog OS lalu mengetiknya di side panel
        (``confirm_approval``). Tanpa diff (hash kosong) ditolak.
        """
        worktree, record = self._resolve_worktree(message)
        current_hash = worktree_mod.diff_hash(worktree)
        if not current_hash:
            return {"ok": False,
                    "error": "Tidak ada perubahan untuk disetujui "
                             "(diff kosong / bukan repo git)."}
        branch = _git_branch(worktree)
        stat = _diff_stat(worktree)
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        approval_id = f"apr-{secrets.token_hex(8)}"
        expires_at = (datetime.now(timezone.utc)
                      + timedelta(minutes=APPROVAL_CODE_TTL_MINUTES))
        self._pending_approvals[approval_id] = {
            "run_id": self._require_str(message, "run_id", ""),
            "repo": record.get("repo", ""),
            "worktree": worktree,
            "branch": branch,
            "diff_hash": current_hash,
            "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "expires_at": expires_at,
            "confirmed": False,
        }
        body = (
            "MUFAKAT Room — setujui commit?\n"
            f"Run: {self._require_str(message, 'run_id', '')}\n"
            f"Repo: {record.get('repo', '')} | Branch: {branch or '-'}\n"
            f"Hash diff: {current_hash}\n"
            f"{stat}\n\n"
            f"KODE PERSETUJUAN: {code}\n"
            "Ketik kode ini di side panel MUFAKAT (berlaku 10 menit).\n"
            "Jangan bagikan kode ini ke AI / chat."
        )
        delivery = _show_human_code("MUFAKAT — Kode Persetujuan Commit", body)
        return {"ok": True, "approval_id": approval_id,
                "diff_hash": current_hash, "branch": branch,
                "diff_stat": stat, "code_delivery": delivery,
                "expires_in_minutes": APPROVAL_CODE_TTL_MINUTES,
                "note": "Kode 6 digit ditampilkan di dialog OS / terminal "
                        "host — ketik di side panel (confirm_approval). "
                        "Kode tidak pernah dikirim lewat kanal ekstensi."}

    def _confirm_approval(self, message: dict) -> dict:
        """Konfirmasi manusia — langkah 2 dari 3 (N3/GPT 3).

        Side panel mengirim kode 6 digit yang diketik manusia. Kode
        dicocokkan dengan hash-nya (constant-time), kedaluwarsa
        diperiksa, dan diff + branch saat ini harus masih sama dengan
        saat ``request_approval``. Berhasil -> persetujuan ditandai
        ``confirmed``; token BARU terbit di ``issue_approval_token``.
        """
        worktree, _record = self._resolve_worktree(message)
        approval_id = self._require_str(message, "approval_id", "")
        code = self._require_str(message, "code", "")
        pending = self._pending_approvals.get(approval_id)
        if pending is None:
            return {"ok": False,
                    "error": "Approval tidak ditemukan / sudah dipakai — "
                             "minta request_approval baru."}
        if pending.get("run_id") != self._require_str(message, "run_id", ""):
            return {"ok": False, "error": "approval_id tidak cocok dengan run_id."}
        if datetime.now(timezone.utc) > pending["expires_at"]:
            self._pending_approvals.pop(approval_id, None)
            return {"ok": False,
                    "error": "Kode persetujuan kedaluwarsa — "
                             "minta request_approval baru."}
        if not code or not hmac.compare_digest(
                hashlib.sha256(code.encode("utf-8")).hexdigest(),
                pending["code_hash"]):
            return {"ok": False, "error": "Kode persetujuan salah."}
        current_hash = worktree_mod.diff_hash(worktree)
        if not current_hash or not hmac.compare_digest(
                current_hash, pending["diff_hash"]):
            return {"ok": False,
                    "error": "Diff berubah sejak request_approval — "
                             "minta request_approval baru."}
        if _git_branch(worktree) != pending["branch"]:
            return {"ok": False,
                    "error": "Branch berubah sejak request_approval — "
                             "minta request_approval baru."}
        pending["confirmed"] = True
        return {"ok": True, "approval_id": approval_id, "confirmed": True,
                "diff_hash": current_hash}

    def _issue_approval_token(self, message: dict) -> dict:
        """Terbitkan token commit sekali pakai — langkah 3 dari 3.

        HANYA bila ada persetujuan manusia yang sudah dikonfirmasi
        (``confirm_approval`` dengan kode 6 digit dari dialog OS) untuk
        run_id ini dan hash diff yang sama. Pemanggil yang sama TIDAK
        BISA menerbitkan token sendiri (N3): tanpa ``request_approval``
        + ``confirm_approval`` manusia, perintah ini ditolak.
        """
        worktree, _record = self._resolve_worktree(message)
        shown_hash = self._require_str(message, "diff_hash", "")
        if not shown_hash:
            raise ValueError("Field 'diff_hash' wajib diisi.")
        run_id = self._require_str(message, "run_id", "")
        confirmed = None
        for approval_id, pending in list(self._pending_approvals.items()):
            if (pending.get("run_id") == run_id
                    and pending.get("confirmed")
                    and pending.get("diff_hash") == shown_hash):
                confirmed = (approval_id, pending)
                break
        if confirmed is None:
            return {"ok": False,
                    "error": "Token tidak bisa diterbitkan tanpa persetujuan "
                             "manusia: kirim request_approval, ketik kode "
                             "6 digit dari dialog OS di side panel "
                             "(confirm_approval), lalu ulangi."}
        approval_id, pending = confirmed
        current_hash = worktree_mod.diff_hash(worktree)
        if not current_hash or not hmac.compare_digest(shown_hash, current_hash):
            return {"ok": False,
                    "error": "Hash diff tidak cocok dengan diff saat ini — "
                             "tampilkan ulang diff terbaru sebelum Approve."}
        if _git_branch(worktree) != pending["branch"]:
            return {"ok": False,
                    "error": "Branch berubah sejak disetujui — "
                             "minta persetujuan baru."}
        token = secrets.token_urlsafe(32)
        self._issued_token = token
        self._issued_diff_hash = current_hash
        self._issued_branch = pending["branch"]
        self._approval_used = False
        self._pending_approvals.pop(approval_id, None)
        return {"ok": True, "approval_token": token,
                "diff_hash": current_hash}

    def _commit(self, message: dict) -> dict:
        worktree, _record = self._resolve_worktree(message)
        token = message.get("approval_token")
        if not isinstance(token, str):
            return {"ok": False,
                    "error": "commit ditolak: butuh approval token yang valid dari UI."}
        # Token boleh dari konstruktor (uji / token yang disetel di awal)
        # atau token yang diterbitkan issue_approval_token.
        token_ok = False
        if self._issued_token is not None:
            token_ok = hmac.compare_digest(token, self._issued_token)
            if token_ok and self._issued_diff_hash is not None:
                current_hash = worktree_mod.diff_hash(worktree)
                if not current_hash or not hmac.compare_digest(
                        current_hash, self._issued_diff_hash):
                    return {"ok": False,
                            "error": "commit ditolak: diff berubah sejak "
                                     "disetujui — minta persetujuan baru."}
            if token_ok and self._issued_branch is not None:
                if _git_branch(worktree) != self._issued_branch:
                    return {"ok": False,
                            "error": "commit ditolak: branch berubah sejak "
                                     "disetujui — minta persetujuan baru."}
        elif self.approval_token is not None:
            token_ok = hmac.compare_digest(token, self.approval_token)
        if not token_ok or self._approval_used:
            return {
                "ok": False,
                "error": "commit ditolak: butuh approval token yang valid dari UI.",
            }
        self._approval_used = True
        # N2 (putaran 2): teruskan hash yang disetujui ke commit() —
        # commit memverifikasi ulang hash staged SEBELUM commit, jadi
        # file yang ditambahkan setelah Approve tidak bisa ikut
        # ter-commit diam-diam.
        issued_hash = self._issued_diff_hash
        self._issued_token = None
        self._issued_diff_hash = None
        self._issued_branch = None
        return {
            "ok": True,
            "committed": worktree_mod.commit(
                worktree,
                self._require_str(message, "message", "MUFAKAT Room"),
                expected_diff_hash=issued_hash,
            ),
        }

    def _cleanup(self, message: dict) -> dict:
        worktree, record = self._resolve_worktree(message)
        repo_path = registry_mod.resolve_repo(record.get("repo", ""))
        removed = worktree_mod.cleanup(
            worktree, str(repo_path) if repo_path is not None else None)
        if removed:
            registry_mod.remove_run(self._require_str(message, "run_id", ""))
        return {"ok": True, "removed": removed}

    def _status(self, message: dict) -> dict:
        return {
            "ok": True,
            "runner": "mufakat-room",
            "docker_available": sandbox_mod.docker_available(),
            "mode": "manual_handoff",
        }


def handle_command(message: dict, approval_token: str | None = None) -> dict:
    """Fungsi sekali pakai (untuk test / pemanggil sederhana)."""
    return RunnerHost(approval_token=approval_token).handle_command(message)


def serve(approval_token: str | None = None) -> None:
    """Loop native messaging di stdin/stdout (binary, length-prefixed)."""
    host = RunnerHost(approval_token=approval_token)
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        header = stdin.read(4)
        if len(header) < 4:
            break  # stdin ditutup (Chrome menutup host) -> keluar
        (length,) = struct.unpack("<I", header)
        if length > MAX_MESSAGE_BYTES:
            # Pesan raksasa tidak dibaca (stream tidak bisa di-resync
            # dengan aman) — balas error lalu keluar; Chrome me-restart host.
            stdout.write(encode_message(
                {"ok": False, "error": f"Pesan melebihi batas {MAX_MESSAGE_BYTES} byte."}
            ))
            stdout.flush()
            break
        data = stdin.read(length)
        if len(data) < length:
            break
        try:
            message = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            stdout.write(encode_message({"ok": False, "error": "Payload bukan JSON."}))
            stdout.flush()
            continue
        if not isinstance(message, dict):
            stdout.write(encode_message({"ok": False, "error": "Payload harus object."}))
            stdout.flush()
            continue
        stdout.write(encode_message(host.handle_command(message)))
        stdout.flush()


def main(argv: list[str] | None = None) -> int:
    """Entry point: ``mufakat-room-runner`` / ``mufakat-runner-host``.

    Tanpa subperintah: jalankan host native messaging (``serve()``).
    ``register <nama> <path>``: daftarkan repo ke registry — SATU-SATUNYA
    cara mendaftarkan repo (audit N3: ``register_repo`` TIDAK tersedia
    lewat pesan native messaging). HOME / leluhur HOME ditolak dan
    path harus repo git.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="MUFAKAT Room Local Runner — native messaging host.")
    sub = parser.add_subparsers(dest="command")
    reg = sub.add_parser(
        "register",
        help="Daftarkan repo ke registry (hanya lewat CLI lokal).")
    reg.add_argument("name", help="Nama repo, mis. repo-saya")
    reg.add_argument("path", help="Path folder repo git")
    args = parser.parse_args(argv)
    if args.command == "register":
        from pathlib import Path as _Path

        try:
            result = registry_mod.register_repo(args.name, args.path)
        except ValueError as exc:
            print(f"Gagal mendaftarkan repo: {exc}", file=sys.stderr)
            return 1
        if not (_Path(result["path"]) / ".git").exists():
            print("Peringatan: path terdaftar bukan root repo git "
                  "(.git tidak ditemukan) — worktree git akan gagal "
                  "sampai path diperbaiki.", file=sys.stderr)
        print(f"Repo terdaftar: {result['name']} -> {result['path']}")
        return 0
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
