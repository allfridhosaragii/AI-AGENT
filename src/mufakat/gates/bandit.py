"""Gate bandit (T10).

Bila binary bandit ada: jalankan bandit JSON. Bila tidak ada:
fallback regex deterministik (eval/exec, os.system, shell=True,
pickle, yaml.load, SQL injection). Tidak pernah raise bila tool hilang.
"""

from __future__ import annotations

import json
import shutil
import subprocess

try:
    from ._scan import scan_patterns
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._scan import scan_patterns  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore

_PATTERNS = [
    ("sql-injection", "HIGH", r"execute\s*\(.*\+",
     "Query SQL dibangun dengan konkatenasi string (rawan SQL injection)."),
    ("sql-injection", "HIGH", r"execute\s*\(f[\"'].*SELECT",
     "Query SQL f-string dengan SELECT (rawan SQL injection)."),
    ("eval-exec", "HIGH", r"\beval\s*\(",
     "Penggunaan eval() (B307)."),
    ("eval-exec", "HIGH", r"\bexec\s*\(",
     "Penggunaan exec() (B102)."),
    ("command-injection", "HIGH", r"os\.system\s*\(",
     "Penggunaan os.system() (B605)."),
    ("command-injection", "MEDIUM", r"subprocess\.[a-z_]+\s*\(.*shell\s*=\s*True",
     "subprocess dengan shell=True (B602)."),
    ("deserialization", "HIGH", r"pickle\.loads?\s*\(",
     "Deserialisasi pickle tidak aman (B301)."),
    ("deserialization", "MEDIUM", r"yaml\.load\s*\(",
     "yaml.load tanpa SafeLoader (B506)."),
    ("weak-crypto", "MEDIUM", r"hashlib\.(md5|sha1)\s*\(",
     "Hash lemah md5/sha1 (B303/B324)."),
]


def _run_binary(target_dir) -> GateResult | None:
    if shutil.which("bandit") is None:
        return None
    try:
        result = subprocess.run(
            ["bandit", "-r", "-f", "json", "-q", str(target_dir)],
            capture_output=True, text=True, timeout=300,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    findings = []
    for item in data.get("results", []) or []:
        findings.append({
            "severity": str(item.get("issue_severity", "MEDIUM")).upper(),
            "file": str(item.get("filename", "")),
            "line": int(item.get("line_number", 0) or 0),
            "rule": str(item.get("test_id", "bandit")),
            "message": str(item.get("issue_text", "Temuan bandit.")),
        })
    return GateResult(tool="bandit", passed=not findings, findings=findings)


def run(target_dir) -> GateResult:
    """Jalankan gate bandit atas ``target_dir``."""
    try:
        binary = _run_binary(target_dir)
    except Exception:
        binary = None
    if binary is not None:
        return binary
    findings = scan_patterns(target_dir, _PATTERNS, extensions={".py"})
    return GateResult(tool="bandit", passed=not findings, findings=findings)
