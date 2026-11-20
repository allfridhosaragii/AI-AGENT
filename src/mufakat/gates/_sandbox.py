"""Jembatan gate -> sandbox Docker (audit 20 Nov 2026: C1 + H3;
putaran 2: N1 + N7).

Semua gate WAJIB lewat sini. Bila Docker tidak tersedia, kembalikan
``GateResult(passed=False, rule="sandbox-unavailable")`` — TIDAK
PERNAH fallback ke eksekusi host dan TIDAK PERNAH ``passed=True``.

``sandbox_runner`` adalah injeksi untuk test: callable dengan
signature ``(image, workdir, command, timeout, network_none,
read_only) -> dict`` seperti :func:`mufakat.sandbox.docker.run_in_sandbox`.
Di produksi selalu ``None`` (= runner Docker asli). Test memakai
fake runner supaya gate bisa diuji tanpa Docker sungguhan.

Deteksi Docker (N7): ketersediaan dicek lewat
:func:`mufakat.sandbox.docker.docker_available` — daemon hidup DAN
image sandbox ada — bukan sekadar binary di PATH.
"""

from __future__ import annotations

try:
    from ..sandbox.docker import SANDBOX_IMAGE, docker_available
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates.runner import GateResult  # type: ignore
    from mufakat.sandbox.docker import SANDBOX_IMAGE, docker_available  # type: ignore

SANDBOX_UNAVAILABLE_RULE = "sandbox-unavailable"
TOOL_ERROR_RULE = "tool-error"


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


def tool_error(tool: str, message: str) -> GateResult:
    """GateResult gagal-tertutup saat tool crash / output tak valid (N1).

    Dipakai bila exit code tool di luar daftar suksesnya, atau output
    yang seharusnya JSON kosong/rusak. Dulu kasus ini dianggap
    "0 temuan" (``passed=True``) — verdict AMAN palsu. Sekarang
    ``passed=False`` dengan ``rule="tool-error"`` dan verdict
    :mod:`mufakat.gates.verdict` membacanya sebagai
    ``BELUM_TERVERIFIKASI``.
    """
    return GateResult(tool=tool, passed=False, findings=[{
        "severity": "HIGH", "file": "", "line": 0,
        "rule": TOOL_ERROR_RULE, "message": message,
    }])


def run_gate_in_sandbox(tool: str, target_dir, command: str,
                        timeout: int = 300, read_only: bool = False,
                        sandbox_runner=None, extra_mounts=None) -> dict | GateResult:
    """Jalankan ``command`` di sandbox atas ``target_dir``.

    Kembalikan dict hasil sandbox (``exit_code``/``stdout``/``stderr``),
    atau ``GateResult`` gagal-tertutup bila sandbox tidak tersedia.

    ``extra_mounts``: daftar ``(host_path, container_path)`` yang
    di-mount tambahan di luar worktree (N4: artefak gate). Hanya
    diteruskan ke runner bila tidak kosong, supaya fake runner lama
    yang tidak mengenal parameter itu tetap bisa dipakai.
    """
    runner = sandbox_runner
    if runner is None:
        # Impor di sini (bukan di atas) supaya monkeypatch
        # ``mufakat.sandbox.docker.run_in_sandbox`` di test berlaku.
        from ..sandbox.docker import run_in_sandbox as _fresh_run
        runner = _fresh_run
        # N7: daemon hidup + image ada — binary saja tidak cukup.
        if not docker_available():
            return sandbox_unavailable(
                tool, "Docker tidak tersedia (binary tidak ada, daemon "
                      "tidak merespons `docker info`, atau image "
                      f"{SANDBOX_IMAGE} belum di-build).")
    kwargs: dict = {"timeout": timeout, "network_none": True,
                    "read_only": read_only}
    if extra_mounts:
        kwargs["extra_volumes"] = list(extra_mounts)
    try:
        result = runner(SANDBOX_IMAGE, str(target_dir), command, **kwargs)
    except TypeError:
        # Fake runner lama tanpa parameter extra_volumes: ulangi tanpa
        # mount tambahan (artefak gate lalu tidak terisolasi — hanya
        # jalur test lama; fake runner repo sudah mendukungnya).
        kwargs.pop("extra_volumes", None)
        result = runner(SANDBOX_IMAGE, str(target_dir), command, **kwargs)
    if not isinstance(result, dict):
        return sandbox_unavailable(tool, "runner sandbox mengembalikan tipe tak dikenal.")
    if result.get("sandbox_unavailable"):
        return sandbox_unavailable(tool, str(result.get("stderr", "")))
    return result
