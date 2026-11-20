"""Gate trivy (T10, diperbaiki audit 20 Nov 2026: C1 + H3;
putaran 2: N1).

Dijalankan HANYA di dalam sandbox Docker. Tanpa Docker: gagal
tertutup (``sandbox-unavailable``) — dulu tool tidak ada justru
``passed=True`` (fail-open). Bila binary trivy tidak ada di dalam
sandbox: gagal-tertutup (``tool-missing``), bukan AMAN.
Hanya CVE HIGH/CRITICAL yang fixable yang menggagalkan gate.

N1 — exit code DIPERIKSA (dulu diabaikan; output kosong/rusak
dianggap "0 temuan" -> AMAN palsu):
- trivy ``fs`` keluar 0 bila pemindaian selesai (temuan CVE tidak
  mengubah exit code tanpa ``--exit-code``); selain 0 -> ``tool-error``.
- stdout kosong / bukan JSON -> ``tool-error`` (trivy ``--format json``
  selalu mengeluarkan JSON bila pemindaian selesai).
- DB CVE TIDAK diunduh saat jalan (container ``--network none``):
  dipakai ``--skip-db-update --offline-scan`` dengan DB yang sudah
  dimasukkan ke image saat build (``TRIVY_CACHE_DIR=/var/lib/trivy``,
  lihat ``docker/sandbox.Dockerfile``).
"""

from __future__ import annotations

import json

try:
    from ._sandbox import run_gate_in_sandbox, tool_error, tool_missing
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_error, tool_missing  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate trivy atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "trivy", target_dir,
        "command -v trivy >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "trivy fs --format json --quiet --skip-db-update --offline-scan .",
        timeout=600, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    exit_code = result.get("exit_code")
    if "TOOL_MISSING" in output or exit_code == 127:
        return tool_missing("trivy", "trivy")
    if exit_code != 0:
        return tool_error(
            "trivy",
            f"trivy gagal (exit code {exit_code}, bukan 0) — hasil "
            "tidak dapat dipercaya, bukan AMAN.")
    if not output.strip():
        return tool_error(
            "trivy",
            "trivy tidak mengeluarkan output (stdout kosong) padahal "
            "seharusnya JSON — hasil tidak dapat dipercaya, bukan AMAN.")
    try:
        data = json.loads(output)
    except ValueError:
        return tool_error(
            "trivy", "Output trivy bukan JSON yang valid — hasil tidak "
                     "dapat dipercaya, bukan AMAN.")
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
