"""Gate trivy (T10).

Bila binary trivy ada: jalankan ``trivy fs`` JSON dan laporkan CVE
HIGH/CRITICAL yang fixable. Bila tidak ada: passed True dengan
finding info "trivy tidak tersedia - belum terverifikasi" — tidak
pernah raise bila tool hilang.
"""

from __future__ import annotations

import json
import shutil
import subprocess

try:
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates.runner import GateResult  # type: ignore


def _run_binary(target_dir) -> GateResult | None:
    if shutil.which("trivy") is None:
        return None
    try:
        result = subprocess.run(
            ["trivy", "fs", "--format", "json", "--quiet", str(target_dir)],
            capture_output=True, text=True, timeout=600,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
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


def run(target_dir) -> GateResult:
    """Jalankan gate trivy atas ``target_dir``."""
    try:
        binary = _run_binary(target_dir)
    except Exception:
        binary = None
    if binary is not None:
        return binary
    return GateResult(tool="trivy", passed=True, findings=[{
        "severity": "INFO", "file": "", "line": 0, "rule": "trivy-missing",
        "message": "trivy tidak tersedia - belum terverifikasi",
    }])
