"""Gate semgrep (T10, diperbaiki audit 20 Nov 2026: C1 + H3;
putaran 2: N1).

Dijalankan HANYA di dalam sandbox Docker. Tanpa Docker: gagal
tertutup (``sandbox-unavailable``). Bila binary semgrep tidak ada
di dalam sandbox: gagal-tertutup (``tool-missing``). Pemindai regex
hanya info tambahan (severity INFO) — BUKAN pengganti tool.

N1 — exit code DIPERIKSA (dulu diabaikan: tool crash / output kosong
dianggap "0 temuan" -> AMAN palsu):
- exit 0 = bersih, exit 1 = ada temuan (dengan ``--error``);
  selain itu (2, 124, 127, ...) -> ``passed=False``,
  ``rule="tool-error"``.
- stdout kosong / bukan JSON -> ``tool-error`` (semgrep ``--json``
  selalu mengeluarkan JSON, bahkan saat bersih).
- Aturan TIDAK diunduh saat jalan (``--config auto`` butuh jaringan
  padahal container ``--network none``): dipakai ``--config /rules``
  — salinan ``p/python`` + ``p/secrets`` yang di-pin di dalam image
  (lihat ``docker/sandbox.Dockerfile``). ``--metrics off`` supaya
  tidak ada telemetri / tulis ke HOME.
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

# Exit code semgrep (dengan --error): 0 bersih, 1 ada temuan.
_OK_EXIT_CODES = (0, 1)


def _regex_info_findings(target_dir) -> list[dict]:
    out = []
    for finding in scan_patterns(target_dir, _PATTERNS,
                                 extensions={".py", ".js", ".ts"}):
        finding = dict(finding)
        finding["severity"] = "INFO"
        finding["message"] = "[regex-info, bukan pengganti semgrep] " + finding["message"]
        out.append(finding)
    return out


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate semgrep atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "semgrep", target_dir,
        "command -v semgrep >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "semgrep --json --config /rules --error --metrics off --quiet .",
        timeout=300, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    exit_code = result.get("exit_code")
    if "TOOL_MISSING" in output or exit_code == 127:
        failed = tool_missing("semgrep", "semgrep")
        failed.findings.extend(_regex_info_findings(target_dir))
        return failed
    if exit_code not in _OK_EXIT_CODES:
        return tool_error(
            "semgrep",
            f"semgrep gagal (exit code {exit_code}, bukan 0/1) — "
            "hasil tidak dapat dipercaya, bukan AMAN.")
    if not output.strip():
        return tool_error(
            "semgrep",
            "semgrep tidak mengeluarkan output (stdout kosong) padahal "
            "seharusnya JSON — hasil tidak dapat dipercaya, bukan AMAN.")
    try:
        data = json.loads(output)
    except ValueError:
        return tool_error(
            "semgrep", "Output semgrep bukan JSON yang valid — hasil "
                       "tidak dapat dipercaya, bukan AMAN.")
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
    passed = not any(f["severity"] in ("HIGH", "CRITICAL") for f in findings)
    return GateResult(tool="semgrep", passed=passed, findings=findings)
