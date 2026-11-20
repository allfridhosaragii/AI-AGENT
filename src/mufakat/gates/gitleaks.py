"""Gate gitleaks (T10).

Bila binary gitleaks ada: jalankan gitleaks JSON. Bila tidak ada:
fallback regex deterministik (AWS key, token GitHub/OpenAI, api_key,
password, private key). Tidak pernah raise bila tool hilang.
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


def _run_binary(target_dir) -> GateResult | None:
    if shutil.which("gitleaks") is None:
        return None
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--source", str(target_dir),
             "--no-git", "--format", "json", "--no-banner"],
            capture_output=True, text=True, timeout=300,
        )
        data = json.loads(result.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
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


def run(target_dir) -> GateResult:
    """Jalankan gate gitleaks atas ``target_dir``."""
    try:
        binary = _run_binary(target_dir)
    except Exception:
        binary = None
    if binary is not None:
        return binary
    findings = scan_patterns(target_dir, _PATTERNS)
    return GateResult(tool="gitleaks", passed=not findings, findings=findings)
