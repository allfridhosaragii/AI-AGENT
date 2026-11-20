"""Jembatan gate -> sandbox Docker (audit 20 Nov 2026: C1 + H3).

Semua gate WAJIB lewat sini. Bila Docker tidak tersedia, kembalikan
``GateResult(passed=False, rule="sandbox-unavailable")`` — TIDAK
PERNAH fallback ke eksekusi host dan TIDAK PERNAH ``passed=True``.

``sandbox_runner`` adalah injeksi untuk test: callable dengan
signature ``(image, workdir, command, timeout, network_none,
read_only) -> dict`` seperti :func:`mufakat.sandbox.docker.run_in_sandbox`.
Di produksi selalu ``None`` (= runner Docker asli). Test memakai
fake runner supaya gate bisa diuji tanpa Docker sungguhan.
"""

from __future__ import annotations

import shutil

try:
    from ..sandbox.docker import SANDBOX_IMAGE
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates.runner import GateResult  # type: ignore
    from mufakat.sandbox.docker import SANDBOX_IMAGE  # type: ignore

SANDBOX_UNAVAILABLE_RULE = "sandbox-unavailable"


def sandbox_unavailable(tool: str, detail: str = "") -> GateResult:
    """GateResult gagal-tertutup saat sandbox tidak tersedia."""
    message = "Sandbox Docker tidak tersedia — gate belum terverifikasi."
    if detail:
        message += f" {detail}"
    return GateResult(tool=tool, passed=False, findings=[{
        "severity": "HIGH", "file": "", "line": 0,
        "rule": SANDBOX_UNAVAILABLE_RULE, "message": message,
    }])


def tool_missing(tool: str, binary: str) -> GateResult:
    """GateResult gagal-tertutup saat tool tidak ada di dalam sandbox."""
    return GateResult(tool=tool, passed=False, findings=[{
        "severity": "HIGH", "file": "", "line": 0,
        "rule": "tool-missing",
        "message": f"Tool {binary} tidak tersedia di dalam sandbox — "
                   "gate belum terverifikasi (bukan AMAN).",
    }])


def run_gate_in_sandbox(tool: str, target_dir, command: str,
                        timeout: int = 300, read_only: bool = False,
                        sandbox_runner=None) -> dict | GateResult:
    """Jalankan ``command`` di sandbox atas ``target_dir``.

    Kembalikan dict hasil sandbox (``exit_code``/``stdout``/``stderr``),
    atau ``GateResult`` gagal-tertutup bila sandbox tidak tersedia.
    """
    runner = sandbox_runner
    if runner is None:
        # Impor di sini (bukan di atas) supaya monkeypatch
        # ``mufakat.sandbox.docker.run_in_sandbox`` di test berlaku.
        from ..sandbox.docker import run_in_sandbox as _fresh_run
        runner = _fresh_run
        if shutil.which("docker") is None:
            return sandbox_unavailable(tool)
    result = runner(SANDBOX_IMAGE, str(target_dir), command,
                    timeout=timeout, network_none=True, read_only=read_only)
    if not isinstance(result, dict):
        return sandbox_unavailable(tool, "runner sandbox mengembalikan tipe tak dikenal.")
    if result.get("sandbox_unavailable"):
        return sandbox_unavailable(tool, str(result.get("stderr", "")))
    return result
