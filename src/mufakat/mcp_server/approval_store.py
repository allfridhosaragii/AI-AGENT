"""Penyimpanan approval manusia di SQLite (audit 20 Nov 2026: H1).

Approval HANYA diputuskan manusia lewat CLI ``mufakat approve <id>``
(konfirmasi y/N di TTY) — TIDAK ADA tool MCP yang bisa memutuskan.
Aturan:

- Satu approval = satu baris SQLite (bukan dict memori): status
  ``pending`` -> ``approved``/``rejected``, sekali putus tidak bisa
  diubah lagi. ``decide_approval`` atomik (satu transaksi
  ``BEGIN IMMEDIATE`` + ``UPDATE ... WHERE status='pending'`` —
  dua proses yang memutuskan bersamaan hanya satu yang menang,
  GPT 3).
- Terikat hash diff: saat manusia menyetujui, hash ``git diff`` saat
  itu disimpan; ``git_commit`` menolak bila diff saat commit berbeda.
  Hash kosong DITOLAK (N12): git error / bukan repo tidak boleh
  melewati cek. Approval juga terikat identitas repo, branch, dan
  worktree (GPT 3) bila diikat saat persetujuan.
- Token sekali pakai: diterbitkan saat persetujuan, disimpan HANYA
  sebagai hash SHA-256 (bukan plaintext), masa berlaku 24 jam,
  hangus setelah dipakai commit. Verifikasi + penandaan terpakai
  dilakukan dalam SATU transaksi atomik
  (:func:`verify_and_consume_token`) — tidak ada celah dua proses
  memakai token yang sama sebelum ditandai terpakai (GPT 3).
- Jalur DB: env ``MUFAKAT_APPROVALS_DB`` atau ``runs/approvals.db``.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from mufakat.runner import runs_dir, utcnow
except ImportError:  # pragma: no cover
    from mufakat.runner import runs_dir, utcnow  # type: ignore

TOKEN_TTL_HOURS = 24

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    diff_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    token_hash TEXT,
    expires_at TEXT,
    used INTEGER NOT NULL DEFAULT 0,
    decided_by TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    repo_path TEXT NOT NULL DEFAULT '',
    branch TEXT NOT NULL DEFAULT '',
    worktree TEXT NOT NULL DEFAULT ''
)
"""

# Kolom ikatan repo/branch/worktree (GPT 3) — migrasi untuk DB lama
# yang dibuat sebelum kolom ini ada.
_BINDING_COLUMNS = (
    ("repo_path", "TEXT NOT NULL DEFAULT ''"),
    ("branch", "TEXT NOT NULL DEFAULT ''"),
    ("worktree", "TEXT NOT NULL DEFAULT ''"),
)


def db_path() -> Path:
    """Lokasi file SQLite approval."""
    override = os.environ.get("MUFAKAT_APPROVALS_DB", "").strip()
    if override:
        return Path(override)
    return runs_dir() / "approvals.db"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path is not None else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(approvals)")}
    for column, definition in _BINDING_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE approvals ADD COLUMN {column} {definition}")
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    record = dict(row)
    record["used"] = bool(record.get("used"))
    record.pop("token_hash", None)
    return record


def create_approval(approval_id: str, title: str, run_id: str = "",
                    requested_by: str = "", diff_hash: str = "",
                    path: Path | None = None,
                    repo_path: str = "", branch: str = "",
                    worktree: str = "") -> dict:
    """Buat approval pending; kembalikan record (tanpa token)."""
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO approvals (approval_id, title, run_id, requested_by,"
            " diff_hash, status, created_at, repo_path, branch, worktree)"
            " VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
            (approval_id, title, run_id, requested_by, diff_hash, utcnow(),
             repo_path, branch, worktree),
        )
        conn.commit()
    finally:
        conn.close()
    record = get_approval(approval_id, path)
    assert record is not None
    return record


def get_approval(approval_id: str, path: Path | None = None) -> dict | None:
    """Baca satu approval dari SQLite; None bila tidak ada."""
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row is not None else None


def list_approvals(path: Path | None = None) -> list[dict]:
    """Semua approval (tanpa token hash)."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows]


def decide_approval(approval_id: str, approved: bool, decided_by: str,
                    note: str = "", diff_hash: str = "",
                    path: Path | None = None,
                    repo_path: str = "", branch: str = "",
                    worktree: str = "") -> tuple[dict | None, str | None]:
    """Putuskan approval (HANYA dipanggil CLI manusia, bukan MCP).

    Kembalikan ``(record, token)``: token hanya ada bila disetujui
    (sekali pakai, 24 jam). Approval yang sudah diputus tidak bisa
    diubah lagi. ``diff_hash`` mengikat persetujuan ke diff saat itu;
    ``repo_path``/``branch``/``worktree`` mengikatnya ke identitas
    repo (GPT 3).

    ATOMIK (GPT 3): baca status + update dilakukan dalam satu
    transaksi ``BEGIN IMMEDIATE`` dengan
    ``UPDATE ... WHERE status='pending'`` — bila dua proses memutus
    bersamaan, hanya satu yang menang (``rowcount == 1``); yang kalah
    mendapat record hasil keputusan pertama tanpa token.
    """
    token = None
    token_hash = None
    expires_at = None
    if approved:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires_at = (datetime.now(timezone.utc)
                      + timedelta(hours=TOKEN_TTL_HOURS)).isoformat().replace("+00:00", "Z")
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return None, None
        if row["status"] != "pending":
            conn.rollback()
            return _row_to_dict(row), None
        bound_hash = diff_hash or row["diff_hash"]
        cursor = conn.execute(
            "UPDATE approvals SET status = ?, token_hash = ?, expires_at = ?,"
            " decided_by = ?, note = ?, diff_hash = ?, decided_at = ?,"
            " repo_path = ?, branch = ?, worktree = ?"
            " WHERE approval_id = ? AND status = 'pending'",
            ("approved" if approved else "rejected", token_hash, expires_at,
             decided_by, note, bound_hash, utcnow(),
             repo_path or row["repo_path"], branch or row["branch"],
             worktree or row["worktree"], approval_id),
        )
        if cursor.rowcount != 1:
            # Diputus proses lain di antara baca dan update.
            conn.rollback()
            return get_approval(approval_id, path), None
        conn.commit()
    finally:
        conn.close()
    return get_approval(approval_id, path), token


def _check_binding(record: dict, current_diff_hash: str,
                   repo_path: str = "", branch: str = "") -> str | None:
    """Pesan error bila ikatan approval tidak cocok; None bila cocok.

    Hash kosong DITOLAK (N12): git error / bukan repo tidak boleh
    melewati cek diff. Ikatan repo/branch hanya ditegakkan bila
    tersimpan saat persetujuan (approval lama tanpa ikatan tetap
    bisa dipakai, tapi CLI baru selalu mengikatnya).
    """
    bound = record.get("diff_hash", "")
    if not bound:
        return ("Approval belum terikat hash diff — setujui lewat "
                "`mufakat approve <id>` yang menghitung hash diff.")
    if not current_diff_hash:
        return ("Hash diff saat ini kosong (git error / bukan repo) — "
                "cek diff tidak boleh dilewati; tolak.")
    if current_diff_hash != bound:
        return ("Diff berubah sejak disetujui (hash tidak cocok) — "
                "minta persetujuan baru.")
    stored_repo = record.get("repo_path", "")
    if stored_repo and repo_path:
        try:
            from pathlib import Path as _Path

            same = _Path(stored_repo).resolve() == _Path(repo_path).resolve()
        except OSError:
            same = stored_repo == repo_path
        if not same:
            return ("Repo saat commit berbeda dengan repo saat disetujui "
                    f"({stored_repo} != {repo_path}) — minta persetujuan baru.")
    stored_branch = record.get("branch", "")
    if stored_branch and branch and branch != stored_branch:
        return ("Branch saat commit berbeda dengan branch saat disetujui "
                f"({branch} != {stored_branch}) — minta persetujuan baru.")
    return None


def verify_token(approval_id: str, token: str,
                 current_diff_hash: str = "",
                 path: Path | None = None,
                 repo_path: str = "", branch: str = "") -> tuple[bool, str]:
    """Verifikasi token approval sekali pakai + ikatan hash diff.

    Kembalikan ``(True, "")`` bila valid, else ``(False, alasan)``.
    TIDAK menandai token terpakai — pemanggil yang berhasil commit
    wajib memakai :func:`verify_and_consume_token` (atomik) agar
    tidak ada celah pakai-bersamaan (GPT 3).
    """
    if not approval_id or not token:
        return False, "approval_id/token kosong."
    record = get_approval(approval_id, path)
    if record is None:
        return False, "Approval tidak ditemukan."
    if record["status"] != "approved":
        return False, f"Approval berstatus {record['status']}, bukan approved."
    if record["used"]:
        return False, "Token approval sudah dipakai (sekali pakai)."
    if record.get("expires_at") and utcnow() > str(record["expires_at"]):
        return False, "Token approval sudah kedaluwarsa."
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT token_hash FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    finally:
        conn.close()
    expected = row["token_hash"] if row is not None else None
    if not expected or not hmac.compare_digest(
            hashlib.sha256(token.encode("utf-8")).hexdigest(), expected):
        return False, "Token approval tidak cocok."
    binding_error = _check_binding(record, current_diff_hash,
                                   repo_path=repo_path, branch=branch)
    if binding_error is not None:
        return False, binding_error
    return True, ""


def verify_and_consume_token(approval_id: str, token: str,
                             current_diff_hash: str = "",
                             path: Path | None = None,
                             repo_path: str = "",
                             branch: str = "") -> tuple[bool, str]:
    """Verifikasi token + tandai terpakai dalam SATU transaksi (GPT 3).

    Semua cek :func:`verify_token` (status, token, kedaluwarsa,
    ikatan diff/repo/branch) dan ``UPDATE used=1`` berjalan dalam
    ``BEGIN IMMEDIATE`` — dua proses yang memakai token yang sama
    bersamaan hanya satu yang lolos. Kembalikan ``(True, "")`` bila
    token valid dan kini hangus, else ``(False, alasan)``.
    """
    if not approval_id or not token:
        return False, "approval_id/token kosong."
    conn = _connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            conn.rollback()
            return False, "Approval tidak ditemukan."
        record = _row_to_dict(row)
        if record["status"] != "approved":
            conn.rollback()
            return False, (f"Approval berstatus {record['status']}, "
                           "bukan approved.")
        if record["used"]:
            conn.rollback()
            return False, "Token approval sudah dipakai (sekali pakai)."
        if record.get("expires_at") and utcnow() > str(record["expires_at"]):
            conn.rollback()
            return False, "Token approval sudah kedaluwarsa."
        expected = row["token_hash"]
        if not expected or not hmac.compare_digest(
                hashlib.sha256(token.encode("utf-8")).hexdigest(), expected):
            conn.rollback()
            return False, "Token approval tidak cocok."
        binding_error = _check_binding(record, current_diff_hash,
                                       repo_path=repo_path, branch=branch)
        if binding_error is not None:
            conn.rollback()
            return False, binding_error
        cursor = conn.execute(
            "UPDATE approvals SET used = 1 WHERE approval_id = ? "
            "AND used = 0",
            (approval_id,),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False, "Token approval sudah dipakai (sekali pakai)."
        conn.commit()
        return True, ""
    finally:
        conn.close()


def consume_token(approval_id: str, path: Path | None = None) -> None:
    """Tandai token sudah dipakai (sekali pakai).

    Hanya untuk kompatibilitas pemanggil lama — pemanggil baru WAJIB
    memakai :func:`verify_and_consume_token` (atomik).
    """
    conn = _connect(path)
    try:
        conn.execute("UPDATE approvals SET used = 1 WHERE approval_id = ?",
                     (approval_id,))
        conn.commit()
    finally:
        conn.close()


def diff_hash_for_repo(repo_path: str = ".") -> str:
    """Hash SHA-256 dari ``git diff HEAD`` repo saat ini.

    ``HEAD`` (bukan diff unstaged saja) supaya perubahan yang sudah
    di-stage ikut terikat ke approval.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "diff", "HEAD"],
            capture_output=True, text=True, timeout=60, shell=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return hashlib.sha256(proc.stdout.encode("utf-8")).hexdigest()
