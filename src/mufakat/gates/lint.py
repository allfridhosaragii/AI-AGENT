"""Gate lint (T10).

Bila ruff tersedia: jalankan ``ruff check``. Bila tidak: cek syntax
semua file Python via ``py_compile``. Tidak pernah raise bila tool
hilang; file yang tidak bisa dibaca dilewati.
"""

from __future__ import annotations

import py_compile
import shutil
import subprocess
from pathlib import Path

try:
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates.runner import GateResult  # type: ignore


def _run_ruff(target_dir) -> GateResult | None:
    if shutil.which("ruff") is None:
        return None
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format", "concise", str(target_dir)],
            capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return GateResult(tool="lint", passed=True, findings=[])
    findings = []
    for line in (result.stdout or "").splitlines():
        # Format concise: path:line:col: CODE pesan
        parts = line.split(":", 3)
        if len(parts) == 4:
            findings.append({
                "severity": "MEDIUM", "file": parts[0],
                "line": int(parts[1]) if parts[1].isdigit() else 0,
                "rule": parts[3].strip().split(" ", 1)[0],
                "message": line.strip()[:300],
            })
    if not findings:
        findings.append({
            "severity": "MEDIUM", "file": "", "line": 0,
            "rule": "ruff", "message": "ruff menemukan pelanggaran lint.",
        })
    return GateResult(tool="lint", passed=False, findings=findings)


def _run_py_compile(target_dir) -> GateResult:
    root = Path(target_dir)
    files = [root] if root.is_file() and root.suffix == ".py" else sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts)
    findings = []
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            findings.append({
                "severity": "HIGH", "file": str(path), "line": 0,
                "rule": "syntax-error", "message": f"Syntax error: {exc}",
            })
        except OSError:
            continue
    return GateResult(tool="lint", passed=not findings, findings=findings)


def run(target_dir) -> GateResult:
    """Jalankan gate lint atas ``target_dir``."""
    try:
        binary = _run_ruff(target_dir)
    except Exception:
        binary = None
    if binary is not None:
        return binary
    return _run_py_compile(target_dir)
