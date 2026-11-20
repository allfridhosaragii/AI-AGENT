"""Gate semgrep (T10).

Bila binary semgrep ada: jalankan semgrep JSON. Bila tidak ada:
fallback regex deterministik (SQL injection, eval/exec, os.system).
Tidak pernah raise bila tool hilang.
"""

from __future__ import annotations

import json
import shutil
import subprocess

try:
    from ._scan import scan_patterns
    from .runner import GateResult
except ImportError:  # pragma: no cover - impor absolut sebagai fallback
    from mufakat.gates._scan import scan_patterns  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore

_PATTERNS = [
    ("sql-injection", "HIGH", r"execute\s*\(.*\+",
     "Query SQL dibangun dengan konkatenasi string (rawan SQL injection)."),
    ("sql-injection", "HIGH", r"execute\s*\(f[\"'].*SELECT",
     "Query SQL f-string dengan SELECT (rawan SQL injection)."),
    ("sql-injection", "HIGH", r"SELECT.*\.format\s*\(",
     "Query SQL dibangun dengan .format() (rawan SQL injection)."),
    ("eval-exec", "HIGH", r"\beval\s*\(",
     "Penggunaan eval() — eksekusi kode arbitrer."),
    ("eval-exec", "HIGH", r"\bexec\s*\(",
     "Penggunaan exec() — eksekusi kode arbitrer."),
    ("command-injection", "HIGH", r"os\.system\s*\(",
     "Penggunaan os.system() — rawan command injection."),
    ("command-injection", "MEDIUM", r"os\.popen\s*\(",
     "Penggunaan os.popen() — rawan command injection."),
    ("command-injection", "MEDIUM", r"subprocess\.[a-z_]+\s*\(.*shell\s*=\s*True",
     "subprocess dengan shell=True — rawan command injection."),
]

_SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM", "INFO": "LOW"}


def _run_binary(target_dir) -> GateResult | None:
    if shutil.which("semgrep") is None:
        return None
    try:
        result = subprocess.run(
            ["semgrep", "--json", "--config", "auto", "--quiet", str(target_dir)],
            capture_output=True, text=True, timeout=300,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    findings = []
    for item in data.get("results", []) or []:
        extra = item.get("extra", {}) or {}
        severity = _SEVERITY.get(str(extra.get("severity", "WARNING")).upper(), "MEDIUM")
        findings.append({
            "severity": severity,
            "file": item.get("path", ""),
            "line": int((item.get("start") or {}).get("line", 0) or 0),
            "rule": str(item.get("check_id", "semgrep")),
            "message": str(extra.get("message", "Temuan semgrep.")),
        })
    return GateResult(tool="semgrep", passed=not findings, findings=findings)


def run(target_dir) -> GateResult:
    """Jalankan gate semgrep atas ``target_dir``."""
    try:
        binary = _run_binary(target_dir)
    except Exception:
        binary = None
    if binary is not None:
        return binary
    findings = scan_patterns(target_dir, _PATTERNS, extensions={".py", ".js", ".ts"})
    return GateResult(tool="semgrep", passed=not findings, findings=findings)
