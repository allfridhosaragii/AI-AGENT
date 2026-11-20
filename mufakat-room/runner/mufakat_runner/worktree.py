"""Worktree & apply patch Local Runner (Claude §5, §T11).

Reuse: bila paket ``mufakat`` terpasang, ``init_workspace`` /
``cleanup`` mendelegasikan ke :mod:`mufakat.sandbox.worktree` (logika
yang sama, satu sumber kebenaran). Bila tidak terpasang, fallback lokal
(folder biasa) dipakai — runner tetap bisa jalan mandiri.

``apply_files`` SELALU memakai validasi lokal di sini (tidak didelegasikan):
path absolut atau mengandung ``..`` DITOLAK dengan ``ValueError``
(sebelum file apa pun ditulis).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

__all__ = [
    "validate_rel_path",
    "init_workspace",
    "apply_files",
    "diff",
    "commit",
    "cleanup",
]

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def validate_rel_path(path: str) -> Path:
    """Validasi path relatif di dalam worktree; tolak traversal/absolut.

    Periksa juga separator Windows (``\\``) agar ``..\\..\\win.ini``
    ditolak meski host-nya Linux, drive Windows (``C:\\...`` / ``C:/...``)
    agar tidak jadi path absolut di host Windows, dan byte NUL.
    """
    raw = str(path or "")
    if "\x00" in raw:
        raise ValueError("Path mengandung byte NUL.")
    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith(("/", "\\")):
        raise ValueError(f"Path absolut ditolak: {raw!r}")
    if _DRIVE_RE.match(raw):
        raise ValueError(f"Path absolut Windows ditolak: {raw!r}")
    parts = raw.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"Path traversal ditolak: {raw!r}")
    if raw == "" or raw in (".", "./"):
        raise ValueError("Path kosong ditolak.")
    return candidate


def _resolve_within_root(root: Path, rel: Path) -> Path:
    """Kembalikan target absolut di bawah ``root``; tolak symlink escape.

    Setiap komponen path yang sudah ada diperiksa: bila ada symlink di
    tengah jalan (``link -> /etc``) atau target itu sendiri symlink,
    tulis ditolak — dulu ``write_text`` mengikuti symlink dan menulis
    ke luar worktree.
    """
    root_resolved = root.resolve()
    current = root_resolved
    for part in rel.parts:
        if part in ("", "."):
            continue
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Path melewati symlink ditolak: {rel!r}")
    target = root_resolved / rel
    if target.is_symlink():
        raise ValueError(f"Path symlink ditolak: {rel!r}")
    return target


def init_workspace(repo_path: str | Path, run_id: str) -> Path:
    """Buat worktree ``runs/<run_id>/wt`` di branch ``mufakat/<run_id>``."""
    # Validasi run_id sebelum delegasi: run_id traversal (../../x)
    # dulu lolos ke create_worktree dan membuat folder di luar repo.
    try:
        from mufakat.sandbox.worktree import validate_run_id

        validate_run_id(run_id)
    except ImportError:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", str(run_id)) or ".." in str(run_id):
            raise ValueError(f"run_id tidak valid: {run_id!r}")
    try:
        from mufakat.sandbox.worktree import create_worktree

        return create_worktree(repo_path, run_id)
    except ImportError:
        target = Path(repo_path) / "runs" / run_id / "wt"
        target.mkdir(parents=True, exist_ok=True)
        return target


def _read_text_raw(path: Path) -> str:
    """Baca teks TANPA universal-newline translation (L5): ``read_text``
    mengubah ``\\r\\n`` jadi ``\\n`` sehingga patch applier tidak bisa
    lagi mendeteksi file CRLF. Baca bytes lalu decode agar EOL asli utuh."""
    return path.read_bytes().decode("utf-8")


def _write_text_raw(path: Path, text: str) -> None:
    """Tulis teks verbatim (tanpa translasi newline per-platform)."""
    path.write_bytes(text.encode("utf-8"))


def apply_files(worktree: str | Path, files: list[dict]) -> list[str]:
    """Terapkan daftar file (replace/patch) ke worktree; kembalikan path yang ditulis.

    ``files``: ``[{"path": "src/app.py", "mode": "replace"|"patch",
    "content": "..."}]``. Mode ``patch`` memakai unified diff dan
    diterapkan secara kering dulu (validasi) sebelum ditulis.

    Atomik per panggilan: SEMUA item divalidasi dulu (path, mode,
    isi, symlink) sebelum file pertama ditulis — dulu item kedua yang
    traversal tetap menulis item pertama.
    """
    if not isinstance(files, (list, tuple)):
        raise ValueError("files harus list of dict.")
    root = Path(worktree)
    root_resolved = root.resolve()
    # Fase 1 — validasi semua, tanpa menulis apa pun.
    plan: list[tuple[Path, str, str]] = []
    for item in files or []:
        if not isinstance(item, dict):
            raise ValueError("Setiap item files harus dict.")
        rel = validate_rel_path(str(item.get("path", "")))
        target = _resolve_within_root(root, rel)
        mode = str(item.get("mode", "replace"))
        if mode not in ("replace", "patch"):
            raise ValueError(f"Mode file tidak dikenal: {mode!r}")
        content = item.get("content", "")
        if not isinstance(content, str):
            raise ValueError(f"content harus string untuk {rel!r}.")
        if mode == "patch":
            # Validasi patch secara kering sebelum menulis apa pun.
            original = _read_text_raw(target) if target.is_file() else ""
            _apply_unified_diff(original, content)
        plan.append((target, mode, content))
    # Fase 2 — tulis.
    applied: list[str] = []
    for target, mode, content in plan:
        rel = target.relative_to(root_resolved)
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "patch":
            original = _read_text_raw(target) if target.is_file() else ""
            _write_text_raw(target, _apply_unified_diff(original, content))
        else:
            _write_text_raw(target, content)
        applied.append(str(rel))
    return applied


def _apply_unified_diff(original: str, patch_text: str) -> str:
    """Terapkan unified diff sederhana (hunk @@ -a,b +c,d @@, - / + / spasi).

    Patch yang tidak bisa diterapkan bersih DITOLAK (ValueError) — tidak
    pernah ditulis setengah-setengah. Baris konteks (`` ``) dan baris
    hapus (``-``) DIVERIFIKASI terhadap isi asli — dulu keduanya
    diabaikan isinya, sehingga patch dengan konteks/hapus yang salah
    tetap "berhasil" dan merusak file diam-diam. Jumlah baris tiap hunk
    juga diperiksa terhadap angka di header ``@@``.
    """
    if not isinstance(patch_text, str) or not patch_text.strip():
        raise ValueError("Patch kosong.")
    original_lines = original.splitlines(keepends=True)
    # L5 (putaran 2): baris "+" dulu selalu diberi "\n" — file CRLF jadi
    # campur aduk, dan file tanpa newline akhir mendadak punya newline.
    # Pakai akhir baris file ASLI (\r\n bila ada satu saja baris CRLF),
    # dan hormati penanda "\ No newline at end of file".
    eol = "\r\n" if any(line.endswith("\r\n") for line in original_lines) else "\n"
    result: list[str] = []
    patch_lines = patch_text.splitlines()
    i = 0
    src_idx = 0

    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    while i < len(patch_lines):
        line = patch_lines[i]
        match = hunk_re.match(line)
        if match:
            start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            start_idx = max(start - 1, 0) if start > 0 else 0
            if start_idx < src_idx:
                raise ValueError("Patch tidak berurutan / tumpang tindih.")
            result.extend(original_lines[src_idx:start_idx])
            src_idx = start_idx
            i += 1
            old_seen = 0
            new_seen = 0
            # Jenis baris terakhir yang ditambahkan ke result ('plus' /
            # 'context' / None). Penanda "\ No newline at end of file"
            # hanya boleh menghapus newline bila mengikuti baris "+" atau
            # konteks — bila mengikuti baris "-" ia merujuk ke baris yang
            # DIHAPUS (tidak ada di result) dan result tidak boleh diubah.
            last_appended: str | None = None
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                hunk_line = patch_lines[i]
                if hunk_line.startswith("---") or hunk_line.startswith("+++"):
                    i += 1
                    continue
                if hunk_line.startswith("\\"):
                    # "\ No newline at end of file" — penanda sah: hapus
                    # newline dari baris terakhir yang baru ditambahkan
                    # (baris "+" atau konteks) agar file tetap tanpa
                    # newline akhir seperti yang diminta patch.
                    if last_appended is not None and result:
                        last = result[-1]
                        if last.endswith("\r\n"):
                            result[-1] = last[:-2]
                        elif last.endswith("\n"):
                            result[-1] = last[:-1]
                    i += 1
                    continue
                if hunk_line.startswith(" "):
                    if src_idx >= len(original_lines):
                        raise ValueError("Patch melebihi akhir file.")
                    expected = hunk_line[1:]
                    actual = original_lines[src_idx].rstrip("\r\n")
                    if actual != expected:
                        raise ValueError(
                            f"Baris konteks patch tidak cocok: {expected!r} "
                            f"(file berisi {actual!r})."
                        )
                    result.append(original_lines[src_idx])
                    last_appended = "context"
                    src_idx += 1
                    old_seen += 1
                    new_seen += 1
                elif hunk_line.startswith("-"):
                    if src_idx >= len(original_lines):
                        raise ValueError("Patch menghapus baris yang tidak ada.")
                    expected = hunk_line[1:]
                    actual = original_lines[src_idx].rstrip("\r\n")
                    if actual != expected:
                        raise ValueError(
                            f"Baris hapus patch tidak cocok: {expected!r} "
                            f"(file berisi {actual!r})."
                        )
                    last_appended = None
                    src_idx += 1
                    old_seen += 1
                elif hunk_line.startswith("+"):
                    result.append(hunk_line[1:] + eol)
                    last_appended = "plus"
                    new_seen += 1
                elif hunk_line == "":
                    # Baris kosong = baris konteks kosong.
                    if src_idx >= len(original_lines):
                        raise ValueError("Patch melebihi akhir file.")
                    actual = original_lines[src_idx].rstrip("\r\n")
                    if actual != "":
                        raise ValueError(
                            "Baris kosong patch tidak cocok dengan isi file."
                        )
                    result.append(original_lines[src_idx])
                    last_appended = "context"
                    src_idx += 1
                    old_seen += 1
                    new_seen += 1
                else:
                    raise ValueError(f"Baris patch tidak dikenal: {hunk_line!r}")
                i += 1
            if old_seen != old_count or new_seen != new_count:
                raise ValueError(
                    f"Jumlah baris hunk tidak cocok: header @@ -{start},{old_count} "
                    f"+{new_count} tapi isi {old_seen}/{new_seen} baris."
                )
            continue
        if line.startswith(("---", "+++", "diff ", "index ")):
            i += 1
            continue
        raise ValueError(f"Patch tidak diawali hunk @@: {line!r}")
    result.extend(original_lines[src_idx:])
    return "".join(result)


def _stage_all(root: Path) -> bool:
    """Stage semua perubahan (termasuk file baru/untracked) — ``git add -A``.

    N2: ``diff()`` WAJIB memanggil ini dulu. Dulu ``diff()`` memakai
    ``git diff HEAD`` yang TIDAK menampilkan file untracked, sementara
    ``commit()`` memakai ``git add -A`` — file baru (mis. backdoor.py)
    ikut ter-commit tanpa pernah terlihat di diff yang disetujui.
    """
    try:
        result = subprocess.run(
            ["git", "add", "-A"], cwd=str(root),
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def diff(worktree: str | Path) -> str:
    """Unified diff worktree vs HEAD (bila repo git), selain itu ''.

    N2: stage dulu (``git add -A``), lalu ``git diff --cached HEAD`` —
    yang dilihat manusia di diff = yang akan di-commit, termasuk file
    baru. Artefak gate (coverage.json, .coverage, .pytest_cache) tidak
    masuk worktree (ditulis ke mount luar worktree, lihat N4), jadi
    tidak ikut ter-stage di sini.
    """
    root = Path(worktree)
    try:
        if not _stage_all(root):
            return ""
        result = subprocess.run(
            ["git", "diff", "--cached", "HEAD", "--", "."],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass
    return ""


def diff_hash(worktree: str | Path) -> str:
    """Hash SHA-256 dari diff worktree ("" bila tanpa diff / bukan repo)."""
    import hashlib

    text = diff(worktree)
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def commit(worktree: str | Path, message: str,
           expected_diff_hash: str | None = None) -> bool:
    """Commit di worktree. HANYA dipanggil host setelah approval token valid.

    N2: TIDAK ADA lagi ``git add -A`` di sini — yang di-commit HANYA
    yang sudah di-stage oleh ``diff()`` (yang sudah dilihat manusia).
    Bila ``expected_diff_hash`` diberikan, hash diff staged saat ini
    diverifikasi ulang sebelum commit; bila berubah sejak disetujui
    (mis. file baru ditambahkan setelah Approve) -> tolak (False).
    Setelah commit, diverifikasi bahwa tidak ada lagi staged diff
    vs HEAD (commit benar-benar berisi semua yang disetujui).
    Push TIDAK PERNAH dilakukan di sini.
    """
    root = Path(worktree)
    try:
        if expected_diff_hash is not None:
            current = diff_hash(worktree)
            if current != expected_diff_hash:
                return False
        result = subprocess.run(
            ["git", "commit", "-m", message], cwd=str(root),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False
        # Verifikasi ulang: setelah commit, staged diff vs HEAD harus kosong.
        check = subprocess.run(
            ["git", "diff", "--cached", "HEAD", "--", "."],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        return check.returncode == 0 and not check.stdout.strip()
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def cleanup(worktree: str | Path, repo_path: str | Path | None = None) -> bool:
    """Hapus worktree; True bila path sudah tidak ada sesudahnya.

    Fail-closed (audit C2): bila ``repo_path`` diketahui, hapus HANYA
    bila target berada di bawah ``<repo>/runs/<run_id>/wt``. Path di
    luar pola itu (repo itu sendiri, leluhurnya, folder lain) DITOLAK.
    """
    try:
        from mufakat.sandbox.worktree import remove_worktree

        return remove_worktree(worktree, repo_path)
    except ImportError:
        target = Path(worktree)
        try:
            resolved = target.resolve()
        except OSError:
            return False
        if resolved == Path("/") or resolved == Path.home():
            return False
        if repo_path is not None:
            try:
                repo_resolved = Path(repo_path).resolve()
            except OSError:
                repo_resolved = None
            if repo_resolved is not None and (
                resolved == repo_resolved or resolved in repo_resolved.parents
            ):
                return False
            # C2 (fallback lokal): hanya di bawah runs/<run_id>/wt.
            if repo_resolved is None:
                return False
            try:
                rel = resolved.relative_to(repo_resolved / "runs")
            except ValueError:
                return False
            if len(rel.parts) < 2 or rel.parts[1] != "wt":
                return False
        if target.exists() or target.is_symlink():
            try:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            except OSError:
                pass
        return not target.exists() and not target.is_symlink()
