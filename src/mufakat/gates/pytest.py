"""Gate pytest (T10).

Bila ada file test di ``target_dir``: jalankan
``[sys.executable, -m, pytest, -q, target_dir]`` dan parse exit code.
Bila tidak ada test: passed True (info). Bila pytest tidak tersedia
padahal ada test: gagal-terbuka. Tidak pernah raise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates.runner import GateResult  # type: ignore


def _has_tests(target_dir) -> bool:
    root = Path(target_dir)
    if root.is_file():
        return root.name.startswith("test_") or root.name.endswith("_test.py")
    for path in root.rglob("*.py"):
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
    return False


def run(target_dir) -> GateResult:
    """Jalankan gate pytest atas ``target_dir``."""
    if not _has_tests(target_dir):
        return GateResult(tool="pytest", passed=True, findings=[{
            "severity": "INFO", "file": "", "line": 0, "rule": "no-tests",
            "message": "Tidak ada test ditemukan.",
        }])
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", str(target_dir)],
            capture_output=True, text=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GateResult(tool="pytest", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0,
            "rule": "pytest-error", "message": f"pytest tidak dapat dijalankan: {exc}",
        }])
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if "No module named pytest" in output:
        return GateResult(tool="pytest", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0,
            "rule": "pytest-missing", "message": "pytest tidak tersedia.",
        }])
    if result.returncode == 0:
        return GateResult(tool="pytest", passed=True, findings=[])
    findings = []
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("FAILED") or "assert" in line and "::" in line:
            findings.append({
                "severity": "HIGH", "file": "", "line": 0,
                "rule": "test-failed", "message": line[:300],
            })
    if not findings:
        tail = [ln for ln in output.splitlines() if ln.strip()][-3:]
        findings.append({
            "severity": "HIGH", "file": "", "line": 0,
            "rule": "test-failed",
            "message": "pytest gagal (exit code "
                       f"{result.returncode}): " + " | ".join(tail)[:300],
        })
    return GateResult(tool="pytest", passed=False, findings=findings)
