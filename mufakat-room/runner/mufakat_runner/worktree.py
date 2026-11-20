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


def validate_rel_path(path: str) -> Path:
    """Validasi path relatif di dalam worktree; tolak traversal/absolut.

    Periksa juga separator Windows (``\\``) agar ``..\\..\\win.ini``
    ditolak meski host-nya Linux.
    """
    raw = str(path or "")
    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith(("/", "\\")):
        raise ValueError(f"Path absolut ditolak: {raw!r}")
    parts = raw.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"Path traversal ditolak: {raw!r}")
    if raw == "" or raw in (".", "./"):
        raise ValueError("Path kosong ditolak.")
    return candidate


def init_workspace(repo_path: str | Path, run_id: str) -> Path:
    """Buat worktree ``runs/<run_id>/wt`` di branch ``mufakat/<run_id>``."""
    try:
        from mufakat.sandbox.worktree import create_worktree

        return create_worktree(repo_path, run_id)
    except ImportError:
        target = Path(repo_path) / "runs" / run_id / "wt"
        target.mkdir(parents=True, exist_ok=True)
        return target


def apply_files(worktree: str | Path, files: list[dict]) -> list[str]:
    """Terapkan daftar file (replace/patch) ke worktree; kembalikan path yang ditulis.

    ``files``: ``[{"path": "src/app.py", "mode": "replace"|"patch",
    "content": "..."}]``. Mode ``patch`` memakai unified diff dan
    diterapkan secara kering dulu (validasi) sebelum ditulis.
    """
    root = Path(worktree)
    applied: list[str] = []
    for item in files or []:
        rel = validate_rel_path(str(item.get("path", "")))
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = str(item.get("mode", "replace"))
        content = str(item.get("content", ""))
        if mode == "patch":
            original = target.read_text(encoding="utf-8") if target.is_file() else ""
            patched = _apply_unified_diff(original, content)
            target.write_text(patched, encoding="utf-8")
        elif mode == "replace":
            target.write_text(content, encoding="utf-8")
        else:
            raise ValueError(f"Mode file tidak dikenal: {mode!r}")
        applied.append(str(rel))
    return applied


def _apply_unified_diff(original: str, patch_text: str) -> str:
    """Terapkan unified diff sederhana (hunk @@ -a,b +c,d @@, - / + / spasi).

    Patch yang tidak bisa diterapkan bersih DITOLAK (ValueError) — tidak
    pernah ditulis setengah-setengah.
    """
    original_lines = original.splitlines(keepends=True)
    result: list[str] = []
    patch_lines = patch_text.splitlines()
    i = 0
    src_idx = 0
    import re

    hunk_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
    while i < len(patch_lines):
        line = patch_lines[i]
        match = hunk_re.match(line)
        if match:
            start = int(match.group(1))
            start_idx = max(start - 1, 0) if start > 0 else 0
            if start_idx < src_idx:
                raise ValueError("Patch tidak berurutan / tumpang tindih.")
            result.extend(original_lines[src_idx:start_idx])
            src_idx = start_idx
            i += 1
            while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
                hunk_line = patch_lines[i]
                if hunk_line.startswith("---") or hunk_line.startswith("+++"):
                    i += 1
                    continue
                if hunk_line.startswith(" "):
                    if src_idx >= len(original_lines):
                        raise ValueError("Patch melebihi akhir file.")
                    result.append(original_lines[src_idx])
                    src_idx += 1
                elif hunk_line.startswith("-"):
                    if src_idx >= len(original_lines):
                        raise ValueError("Patch menghapus baris yang tidak ada.")
                    src_idx += 1
                elif hunk_line.startswith("+"):
                    result.append(hunk_line[1:] + "\n")
                elif hunk_line == "":
                    result.append("\n")
                else:
                    raise ValueError(f"Baris patch tidak dikenal: {hunk_line!r}")
                i += 1
            continue
        if line.startswith(("---", "+++", "diff ", "index ")):
            i += 1
            continue
        raise ValueError(f"Patch tidak diawali hunk @@: {line!r}")
    result.extend(original_lines[src_idx:])
    return "".join(result)


def diff(worktree: str | Path) -> str:
    """Unified diff worktree vs HEAD (bila repo git), selain itu ''."""
    root = Path(worktree)
    try:
        result = subprocess.run(
            ["git", "diff", "--", "."],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass
    return ""


def commit(worktree: str | Path, message: str) -> bool:
    """Commit di worktree. HANYA dipanggil host setelah approval token valid.

    Push TIDAK PERNAH dilakukan di sini.
    """
    root = Path(worktree)
    try:
        add = subprocess.run(
            ["git", "add", "-A"], cwd=str(root),
            capture_output=True, text=True, timeout=60,
        )
        if add.returncode != 0:
            return False
        result = subprocess.run(
            ["git", "commit", "-m", message], cwd=str(root),
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def cleanup(worktree: str | Path, repo_path: str | Path | None = None) -> bool:
    """Hapus worktree; True bila path sudah tidak ada sesudahnya."""
    try:
        from mufakat.sandbox.worktree import remove_worktree

        return remove_worktree(worktree, repo_path)
    except ImportError:
        target = Path(worktree)
        if target.exists():
            try:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            except OSError:
                pass
        return not target.exists()
