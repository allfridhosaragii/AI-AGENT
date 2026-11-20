"""Gate pytest (T10, diperbaiki audit 20 Nov 2026: C1 + H3).

Dijalankan HANYA di dalam sandbox Docker via
:mod:`mufakat.gates._sandbox` — TIDAK PERNAH di host. Tanpa Docker:
``passed=False``, ``rule="sandbox-unavailable"``, verdict
``BELUM_TERVERIFIKASI``.

- Tidak ada test -> GAGAL (``no-tests``): kode baru tanpa test
  tidak boleh lolos.
- Coverage NYATA: ``pytest --cov=. --cov-report=json:coverage.json``;
  nilai dibaca dari ``coverage.json`` di ``target_dir`` dan disimpan
  di ``GateResult.coverage`` untuk :func:`mufakat.gates.verdict.verdict`.
- pytest tidak tersedia di dalam sandbox -> gagal-tertutup
  (``pytest-missing``), bukan AMAN.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from ._sandbox import run_gate_in_sandbox
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore


def _has_tests(target_dir) -> bool:
    root = Path(target_dir)
    if root.is_file():
        return root.name.startswith("test_") or root.name.endswith("_test.py")
    for path in root.rglob("*.py"):
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
    return False


def _read_coverage(target_dir) -> float | None:
    """Baca persen coverage dari coverage.json yang ditulis sandbox."""
    try:
        data = json.loads((Path(target_dir) / "coverage.json").read_text(encoding="utf-8"))
        total = data.get("totals", {}).get("percent_covered")
        return float(total) / 100.0 if total is not None else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate pytest atas ``target_dir`` (di sandbox)."""
    if not _has_tests(target_dir):
        return GateResult(tool="pytest", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0, "rule": "no-tests",
            "message": "Tidak ada test ditemukan — kode tanpa test gagal (fail-closed).",
        }])
    result = run_gate_in_sandbox(
        "pytest", target_dir,
        "python -m pytest -q --cov=. --cov-report=json:coverage.json .",
        timeout=600, read_only=False, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = (result.get("stdout") or "") + "\n" + (result.get("stderr") or "")
    coverage = _read_coverage(target_dir)
    if "No module named pytest" in output:
        return GateResult(tool="pytest", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0,
            "rule": "pytest-missing",
            "message": "pytest tidak tersedia di dalam sandbox.",
        }], coverage=coverage)
    if result.get("exit_code") == 0:
        findings = []
        if coverage is not None:
            findings.append({
                "severity": "INFO", "file": "", "line": 0,
                "rule": "coverage",
                "message": f"Coverage terukur: {coverage * 100:.1f}%.",
            })
        return GateResult(tool="pytest", passed=True, findings=findings,
                          coverage=coverage)
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
                       f"{result.get('exit_code')}: " + " | ".join(tail)[:300],
        })
    return GateResult(tool="pytest", passed=False, findings=findings,
                      coverage=coverage)
