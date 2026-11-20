"""Local Runner MUFAKAT Room — Native Messaging host (Claude §5, §T11).

Protokol: stdin/stdout length-prefixed JSON (Chrome Native Messaging):
4 byte little-endian panjang + payload JSON UTF-8.

Perintah yang diterima (JSON)::

    {"command": "init_workspace", "repo_path": "...", "run_id": "..."}
    {"command": "apply_files", "worktree": "...", "files": [{"path", "mode", "content"}]}
    {"command": "run_gates", "profile": "python|node", "target_dir": "..."}
    {"command": "diff", "worktree": "..."}
    {"command": "commit", "worktree": "...", "message": "...", "approval_token": "..."}
    {"command": "cleanup", "worktree": "...", "repo_path": "..."}
    {"command": "status"}

Keamanan:
- ``commit`` HANYA jalan bila ``approval_token`` cocok dengan token yang
  diberikan pengguna lewat UI (token sekali pakai, disimpan di memori
  host saja — bukan di disk). Tanpa token: ditolak.
- ``apply_files`` menolak path traversal (``..``, absolut) — lihat
  :mod:`mufakat_runner.worktree`.
- Runner hanya menerima perintah dari ID ekstensi yang terdaftar
  (``allowed_origins`` di manifest host, lihat ``install_host.py``).
  Host TIDAK membuka port jaringan apa pun.
- Tidak ada auto-send / otomasi situs AI di sini: runner hanya mengurus
  worktree + gates lokal.
"""

from __future__ import annotations

import json
import struct
import sys

from mufakat_runner import gates as gates_mod
from mufakat_runner import sandbox as sandbox_mod
from mufakat_runner import verdict as verdict_mod
from mufakat_runner import worktree as worktree_mod

__all__ = ["encode_message", "decode_message", "handle_command", "serve", "main"]


def encode_message(payload: dict) -> bytes:
    """Encode satu pesan native messaging (length-prefixed)."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(data)) + data


def decode_message(buffer: bytes) -> tuple[dict, bytes]:
    """Decode satu pesan dari awal ``buffer``; kembalikan (pesan, sisa).

    Melempar ``ValueError`` bila buffer belum berisi satu pesan lengkap.
    """
    if len(buffer) < 4:
        raise ValueError("Buffer belum berisi header panjang pesan.")
    (length,) = struct.unpack("<I", buffer[:4])
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

    # -- dispatch --------------------------------------------------------
    def handle_command(self, message: dict) -> dict:
        command = message.get("command")
        handler = {
            "init_workspace": self._init_workspace,
            "apply_files": self._apply_files,
            "run_gates": self._run_gates,
            "diff": self._diff,
            "commit": self._commit,
            "cleanup": self._cleanup,
            "status": self._status,
        }.get(command)
        if handler is None:
            return {"ok": False, "error": f"Perintah tidak dikenal: {command!r}"}
        try:
            return handler(message)
        except (ValueError, OSError) as exc:
            return {"ok": False, "error": str(exc)}

    # -- perintah ---------------------------------------------------------
    def _init_workspace(self, message: dict) -> dict:
        path = worktree_mod.init_workspace(
            message.get("repo_path", "."), str(message.get("run_id", "room"))
        )
        return {"ok": True, "worktree": str(path)}

    def _apply_files(self, message: dict) -> dict:
        applied = worktree_mod.apply_files(
            message.get("worktree", "."), message.get("files") or []
        )
        return {"ok": True, "applied": applied}

    def _run_gates(self, message: dict) -> dict:
        target = message.get("target_dir") or message.get("worktree") or "."
        results = gates_mod.run_gates(target, profile=message.get("profile", "python"))
        verdict_result = verdict_mod.apply_verdict(results)
        return {"ok": True, "results": results, "verdict": verdict_result}

    def _diff(self, message: dict) -> dict:
        return {"ok": True, "diff": worktree_mod.diff(message.get("worktree", "."))}

    def _commit(self, message: dict) -> dict:
        token = message.get("approval_token")
        if not self.approval_token or token != self.approval_token or self._approval_used:
            return {
                "ok": False,
                "error": "commit ditolak: butuh approval token yang valid dari UI.",
            }
        self._approval_used = True
        return {
            "ok": True,
            "committed": worktree_mod.commit(
                message.get("worktree", "."), str(message.get("message", "MUFAKAT Room"))
            ),
        }

    def _cleanup(self, message: dict) -> dict:
        removed = worktree_mod.cleanup(
            message.get("worktree", "."), message.get("repo_path")
        )
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
