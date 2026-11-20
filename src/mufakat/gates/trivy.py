"""Gate trivy (T10, diperbaiki audit 20 Nov 2026: C1 + H3).

Dijalankan HANYA di dalam sandbox Docker. Tanpa Docker: gagal
tertutup (``sandbox-unavailable``) — dulu tool tidak ada justru
``passed=True`` (fail-open). Bila binary trivy tidak ada di dalam
sandbox: gagal-tertutup (``tool-missing``), bukan AMAN.
Hanya CVE HIGH/CRITICAL yang fixable yang menggagalkan gate.
"""

from __future__ import annotations

import json

try:
    from ._sandbox import run_gate_in_sandbox, tool_missing
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_missing  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate trivy atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "trivy", target_dir,
        "command -v trivy >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "trivy fs --format json --quiet .",
        timeout=600, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    if "TOOL_MISSING" in output or result.get("exit_code") == 127:
        return tool_missing("trivy", "trivy")
    try:
        data = json.loads(output or "{}")
    except ValueError:
        return GateResult(tool="trivy", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0, "rule": "trivy-error",
            "message": "Output trivy bukan JSON yang valid.",
        }])
    findings = []
    for result_item in data.get("Results", []) or []:
        for vuln in result_item.get("Vulnerabilities", []) or []:
            severity = str(vuln.get("Severity", "")).upper()
            fixed = vuln.get("FixedVersion")
            if severity in ("HIGH", "CRITICAL") and fixed:
                findings.append({
                    "severity": severity,
                    "file": str(result_item.get("Target", "")),
                    "line": 0,
                    "rule": str(vuln.get("VulnerabilityID", "trivy")),
                    "message": (
                        f"CVE fixable: {vuln.get('PkgName', '')} "
                        f"{vuln.get('InstalledVersion', '')} -> {fixed} "
                        f"({vuln.get('Title', '')})"
                    ),
                })
    return GateResult(tool="trivy", passed=not findings, findings=findings)
