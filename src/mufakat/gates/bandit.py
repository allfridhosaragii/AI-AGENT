"""Gate bandit (T10, diperbaiki audit 20 Nov 2026: C1 + H3 + H4;
putaran 2: N1).

Dijalankan HANYA di dalam sandbox Docker. Tanpa Docker: gagal
tertutup (``sandbox-unavailable``).

- Hanya HIGH/CRITICAL yang menggagalkan gate; MEDIUM dicatat
  (butuh justifikasi) tetapi tidak menggagalkan — sesuai ``gates.yaml``.
- ``B101`` (assert) dikecualikan untuk file ``test_*.py`` /
  ``*_test.py``: setiap test memakai ``assert``, jadi B101 di test
  tidak boleh membuat AMAN mustahil tercapai.
- Bila binary bandit tidak ada di dalam sandbox: gagal-tertutup
  (``tool-missing``). Pemindai regex hanya info tambahan (severity
  INFO) — BUKAN pengganti tool.

N1 — exit code DIPERIKSA (dulu diabaikan; output non-JSON lewat
``except ValueError: return []`` dianggap "0 temuan" -> AMAN palsu):
- exit 0 = bersih, exit 1 = ada temuan; selain itu -> ``tool-error``.
- stdout kosong / bukan JSON -> ``tool-error`` (bandit ``-f json``
  selalu mengeluarkan JSON, bahkan saat bersih).
"""

from __future__ import annotations

import json

try:
    from ._sandbox import run_gate_in_sandbox, tool_error, tool_missing
    from ._scan import scan_patterns
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_error, tool_missing  # type: ignore
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

_FAIL_SEVERITIES = ("HIGH", "CRITICAL")

# Exit code bandit: 0 bersih, 1 ada temuan.
_OK_EXIT_CODES = (0, 1)


def _is_test_file(filename: str) -> bool:
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py")


def _regex_info_findings(target_dir) -> list[dict]:
    """Temuan regex HANYA sebagai info tambahan (severity INFO)."""
    out = []
    for finding in scan_patterns(target_dir, _PATTERNS, extensions={".py"}):
        finding = dict(finding)
        finding["severity"] = "INFO"
        finding["message"] = "[regex-info, bukan pengganti bandit] " + finding["message"]
        out.append(finding)
    return out


def _parse_bandit_json(stdout: str) -> list[dict]:
    """Parse output JSON bandit; ValueError bila bukan JSON (N1).

    Dulu ``except ValueError: return []`` — output rusak dianggap
    "0 temuan" dan gate lolos. Sekarang error diteruskan ke pemanggil
    dan menjadi ``tool-error`` (gagal-tertutup).
    """
    data = json.loads(stdout)
    findings = []
    for item in data.get("results", []) or []:
        rule = str(item.get("test_id", "bandit"))
        filename = str(item.get("filename", ""))
        # H4: B101 (assert) di file test dikecualikan.
        if rule == "B101" and _is_test_file(filename):
            continue
        severity = str(item.get("issue_severity", "MEDIUM")).upper()
        if severity == "MEDIUM":
            message = str(item.get("issue_text", "Temuan bandit."))
            message += " (MEDIUM — butuh justifikasi, tidak menggagalkan gate.)"
        else:
            message = str(item.get("issue_text", "Temuan bandit."))
        findings.append({
            "severity": severity, "file": filename,
            "line": int(item.get("line_number", 0) or 0),
            "rule": rule, "message": message,
        })
    return findings


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate bandit atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "bandit", target_dir,
        "command -v bandit >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "bandit -r -f json -q .",
        timeout=300, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    exit_code = result.get("exit_code")
    if "TOOL_MISSING" in output or exit_code == 127:
        failed = tool_missing("bandit", "bandit")
        failed.findings.extend(_regex_info_findings(target_dir))
        return failed
    if exit_code not in _OK_EXIT_CODES:
        return tool_error(
            "bandit",
            f"bandit gagal (exit code {exit_code}, bukan 0/1) — hasil "
            "tidak dapat dipercaya, bukan AMAN.")
    if not output.strip():
        return tool_error(
            "bandit",
            "bandit tidak mengeluarkan output (stdout kosong) padahal "
            "seharusnya JSON — hasil tidak dapat dipercaya, bukan AMAN.")
    try:
        findings = _parse_bandit_json(output)
    except ValueError:
        return tool_error(
            "bandit", "Output bandit bukan JSON yang valid — hasil tidak "
                      "dapat dipercaya, bukan AMAN.")
    passed = not any(f["severity"] in _FAIL_SEVERITIES for f in findings)
    return GateResult(tool="bandit", passed=passed, findings=findings)
