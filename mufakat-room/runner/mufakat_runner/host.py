"""Local Runner MUFAKAT Room — Native Messaging host (Claude §5, §T11).

Protokol: stdin/stdout length-prefixed JSON (Chrome Native Messaging):
4 byte little-endian panjang + payload JSON UTF-8.

Perintah yang diterima (JSON) — audit C2: semua perintah memakai
``run_id``, BUKAN path bebas::

    {"command": "register_repo", "name": "repo-saya", "path": "/abs/repo"}
    {"command": "init_workspace", "repo": "repo-saya", "run_id": "..."}
    {"command": "apply_files", "run_id": "...", "files": [{"path", "mode", "content"}]}
    {"command": "run_gates", "run_id": "...", "profile": "python|node"}
    {"command": "diff", "run_id": "..."}
    {"command": "issue_approval_token", "run_id": "...", "diff_hash": "..."}
    {"command": "commit", "run_id": "...", "message": "...", "approval_token": "..."}
    {"command": "cleanup", "run_id": "..."}
    {"command": "status"}

Keamanan:
- Repo HANYA dari registry pengguna ``~/.mufakat/runner.json``
  (lihat :mod:`mufakat_runner.registry`); pesan tidak boleh membawa
  path repo/worktree bebas.
- ``cleanup`` hanya menghapus di bawah ``<repo>/runs/<run_id>/wt``.
- ``commit`` HANYA jalan bila ``approval_token`` cocok dengan token
  yang diterbitkan lewat ``issue_approval_token`` (aliran normal:
  UI menampilkan diff + hash, pengguna klik Approve, host
  memverifikasi hash diff saat ini sama, lalu menerbitkan token
  sekali pakai yang terikat hash itu). Tanpa token: ditolak.
- ``apply_files`` menolak path traversal (``..``, absolut) — lihat
  :mod:`mufakat_runner.worktree`.
- Runner hanya menerima perintah dari ID ekstensi yang terdaftar
  (``allowed_origins`` di manifest host, lihat ``install_host.py``).
  Host TIDAK membuka port jaringan apa pun.
- Tidak ada auto-send / otomasi situs AI di sini: runner hanya mengurus
  worktree + gates lokal.
"""

from __future__ import annotations

import hmac
import json
import secrets
import struct
import sys

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

    # -- dispatch --------------------------------------------------------
    def handle_command(self, message: dict) -> dict:
        if not isinstance(message, dict):
            return {"ok": False, "error": "Perintah harus object JSON."}
        command = message.get("command")
        handler = {
            "register_repo": self._register_repo,
            "init_workspace": self._init_workspace,
            "apply_files": self._apply_files,
            "run_gates": self._run_gates,
            "diff": self._diff,
            "issue_approval_token": self._issue_approval_token,
            "commit": self._commit,
            "cleanup": self._cleanup,
            "status": self._status,
        }.get(command)
        if handler is None:
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
    def _register_repo(self, message: dict) -> dict:
        name = self._require_str(message, "name", "")
        path = self._require_str(message, "path", "")
        if not name or not path:
            raise ValueError("Field 'name' dan 'path' wajib diisi.")
        result = registry_mod.register_repo(name, path)
        return {"ok": True, **result}

    def _init_workspace(self, message: dict) -> dict:
        repo_arg = message.get("repo", message.get("repo_path", "."))
        if not isinstance(repo_arg, str):
            raise ValueError("Field 'repo' harus string.")
        repo_path = registry_mod.resolve_repo(repo_arg)
        if repo_path is None:
            return {"ok": False,
                    "error": f"Repo belum terdaftar di ~/.mufakat/runner.json: {repo_arg!r}. "
                             "Daftarkan dulu lewat perintah register_repo."}
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

    def _issue_approval_token(self, message: dict) -> dict:
        """Terbitkan token commit sekali pakai (aliran normal H6).

        UI menampilkan diff + hash; pengguna klik Approve -> ekstensi
        mengirim ``diff_hash`` yang ditampilkan. Host menghitung hash
        diff saat ini dan HANYA menerbitkan token bila sama — jadi
        token terikat ke diff yang sudah dilihat manusia.
        """
        worktree, _record = self._resolve_worktree(message)
        shown_hash = self._require_str(message, "diff_hash", "")
        if not shown_hash:
            raise ValueError("Field 'diff_hash' wajib diisi.")
        current_hash = worktree_mod.diff_hash(worktree)
        if not hmac.compare_digest(shown_hash, current_hash):
            return {"ok": False,
                    "error": "Hash diff tidak cocok dengan diff saat ini — "
                             "tampilkan ulang diff terbaru sebelum Approve."}
        token = secrets.token_urlsafe(32)
        self._issued_token = token
        self._issued_diff_hash = current_hash
        self._approval_used = False
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
                if not hmac.compare_digest(current_hash, self._issued_diff_hash):
                    return {"ok": False,
                            "error": "commit ditolak: diff berubah sejak "
                                     "disetujui — minta persetujuan baru."}
        elif self.approval_token is not None:
            token_ok = hmac.compare_digest(token, self.approval_token)
        if not token_ok or self._approval_used:
            return {
                "ok": False,
                "error": "commit ditolak: butuh approval token yang valid dari UI.",
            }
        self._approval_used = True
        self._issued_token = None
        self._issued_diff_hash = None
        return {
            "ok": True,
            "committed": worktree_mod.commit(
                worktree,
                self._require_str(message, "message", "MUFAKAT Room"),
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


def main() -> None:
    """Entry point: ``python -m mufakat_runner.host``."""
    serve()


if __name__ == "__main__":
    main()
