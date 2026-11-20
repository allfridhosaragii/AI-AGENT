"""Gate lint (T10, diperbaiki audit 20 Nov 2026: C1 + H3;
putaran 2: N1).

Dijalankan HANYA di dalam sandbox Docker (``ruff check``). Tanpa
Docker: gagal tertutup (``sandbox-unavailable``). Bila ruff tidak
ada di dalam sandbox: gagal-tertutup (``tool-missing``) — fallback
``py_compile`` di host sudah dihapus; syntax check host bukan
pengganti ruff.

N1 — exit code DIPERIKSA (dulu semua nonzero dianggap "ada temuan
lint"): ruff keluar 0 = bersih, 1 = ada pelanggaran; 2 (error,
mis. config rusak / crash) dan lainnya -> ``passed=False``,
``rule="tool-error"``. Exit 1 dengan stdout kosong juga
``tool-error`` (ruff selalu mencetak pelanggaran yang ditemukannya).
"""

from __future__ import annotations

try:
    from ._sandbox import run_gate_in_sandbox, tool_error, tool_missing
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_error, tool_missing  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate lint atas ``target_dir`` (di sandbox)."""
    result = run_gate_in_sandbox(
        "lint", target_dir,
        "command -v ruff >/dev/null 2>&1 || { echo TOOL_MISSING; exit 127; }; "
        "ruff check --output-format concise .",
        timeout=300, read_only=True, sandbox_runner=sandbox_runner)
    if isinstance(result, GateResult):
        return result
    output = result.get("stdout") or ""
    exit_code = result.get("exit_code")
    if "TOOL_MISSING" in output or exit_code == 127:
        return tool_missing("lint", "ruff")
    if exit_code == 0:
        return GateResult(tool="lint", passed=True, findings=[])
    if exit_code != 1:
        return tool_error(
            "lint",
            f"ruff gagal (exit code {exit_code}, bukan 0/1) — hasil "
            "tidak dapat dipercaya, bukan AMAN.")
    if not output.strip():
        return tool_error(
            "lint",
            "ruff keluar 1 (ada pelanggaran) tapi stdout kosong — hasil "
            "tidak dapat dipercaya, bukan AMAN.")
    findings = []
    for line in output.splitlines():
        # Format concise: path:line:col: CODE pesan
        parts = line.split(":", 3)
        if len(parts) == 4:
            findings.append({
                "severity": "MEDIUM", "file": parts[0],
                "line": int(parts[1]) if parts[1].isdigit() else 0,
                "rule": parts[3].strip().split(" ", 1)[0],
                "message": line.strip()[:300],
            })
    if not findings:
        findings.append({
            "severity": "MEDIUM", "file": "", "line": 0,
            "rule": "ruff", "message": "ruff menemukan pelanggaran lint.",
        })
    return GateResult(tool="lint", passed=False, findings=findings)
