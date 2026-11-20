"""Gate gitleaks (T10, diperbaiki audit 20 Nov 2026: C1 + H3).

Dijalankan HANYA di dalam sandbox Docker. Tanpa Docker: gagal
tertutup (``sandbox-unavailable``). Bila binary gitleaks tidak ada
di dalam sandbox: gagal-tertutup (``tool-missing``). Pemindai regex
hanya info tambahan (severity INFO) — BUKAN pengganti tool.
"""

from __future__ import annotations

import json

try:
    from ._sandbox import run_gate_in_sandbox, tool_missing
    from ._scan import scan_patterns
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_missing  # type: ignore
    from mufakat.gates._scan import scan_patterns  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore

_PATTERNS = [
    ("aws-access-key", "CRITICAL", r"AKIA[0-9A-Z]{16}",
     "Secret terdeteksi: AWS access key."),
    ("github-token", "HIGH", r"ghp_[A-Za-z0-9]{20,}",
     "Secret terdeteksi: GitHub personal access token."),
    ("openai-key", "HIGH", r"sk-[A-Za-z0-9]{20,}",
     "Secret terdeteksi: OpenAI API key."),
    ("api-key", "HIGH", r"api_key\s*=\s*[\"'][^\"']+[\"']",
     "Secret terdeteksi: api_key hard-coded."),
    ("password", "HIGH", r"password\s*=\s*[\"'][^\"']+[\"']",
     "Secret terdeteksi: password hard-coded."),
    ("aws-secret-key", "HIGH", r"aws_secret_access_key\s*=\s*[\"'][^\"']+[\"']",
     "Secret terdeteksi: AWS secret access key."),
    ("private-key", "CRITICAL", r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----",
     "Secret terdeteksi: private key."),
    ("generic-secret", "HIGH", r"secret\s*=\s*[\"'][A-Za-z0-9_\-]{8,}[\"']",
     "Secret terdeteksi: nilai secret hard-coded."),
]


def _regex_info_findings(target_dir) -> list[dict]:
    out = []
    for finding in scan_patterns(target_dir, _PATTERNS):
        finding = dict(finding)
        finding["severity"] = "INFO"
        finding["message"] = "[regex-info, bukan pengganti gitleaks] " + finding["message"]
        out.append(finding)
    return out


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate gitleaks atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "gitleaks", target_dir,
        "command -v gitleaks >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "gitleaks detect --source . --no-git --format json --no-banner",
        timeout=300, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    if "TOOL_MISSING" in output or result.get("exit_code") == 127:
        failed = tool_missing("gitleaks", "gitleaks")
        failed.findings.extend(_regex_info_findings(target_dir))
        return failed
    try:
        data = json.loads(output or "[]")
    except ValueError:
        # gitleaks keluar 0 + stdout kosong = tidak ada secret.
        if result.get("exit_code") == 0 and not output.strip():
            return GateResult(tool="gitleaks", passed=True, findings=[])
        return GateResult(tool="gitleaks", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0, "rule": "gitleaks-error",
            "message": "Output gitleaks bukan JSON yang valid.",
        }])
    findings = []
    for item in data if isinstance(data, list) else []:
        findings.append({
            "severity": "HIGH",
            "file": str(item.get("File", "")),
            "line": int(item.get("StartLine", 0) or 0),
            "rule": str(item.get("RuleID", "gitleaks")),
            "message": f"Secret terdeteksi: {item.get('Description', '')}".strip(),
        })
    return GateResult(tool="gitleaks", passed=not findings, findings=findings)
