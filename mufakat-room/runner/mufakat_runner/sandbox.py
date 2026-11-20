"""Sandbox Docker Local Runner (Claude §5; putaran 2: N7).

Reuse: bila paket ``mufakat`` terpasang, eksekusi didelegasikan ke
:mod:`mufakat.sandbox.docker` (user non-root, ``--network none`` saat
test, limit CPU/RAM/waktu). Bila Docker tidak tersedia, fungsi mengembalikan
hasil "belum terverifikasi" (exit 127) — TIDAK PERNAH pura-pura jalan.

N7: ``docker_available()`` BUKAN lagi sekadar binary di PATH.
Binary tanpa daemon (mis. Docker Desktop belum dibuka) dulu
dilaporkan "tersedia". Sekarang: daemon harus merespons
``docker info`` (timeout 5 detik) DAN image ``mufakat-sandbox``
harus ada (``docker image inspect``). Gagal di salah satunya ->
False, dan ``status`` runner melapor jujur (``docker_available:
false``). Bila paket ``mufakat`` tidak terpasang, pemeriksaan yang
sama dilakukan lokal di sini (bukan ``shutil.which`` saja).
"""

from __future__ import annotations

import shutil
import subprocess

__all__ = ["docker_available", "run_in_sandbox", "build_image"]

SANDBOX_IMAGE = "mufakat-sandbox"
_PROBE_TIMEOUT = 5


def _probe_ok(args: list[str]) -> bool:
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=_PROBE_TIMEOUT)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def _daemon_available_locally() -> bool:
    """Cek daemon + image secara lokal (bila paket mufakat tak ada)."""
    if shutil.which("docker") is None:
        return False
    return (_probe_ok(["docker", "info"])
            and _probe_ok(["docker", "image", "inspect", SANDBOX_IMAGE]))


def docker_available() -> bool:
    """True HANYA bila daemon Docker hidup DAN image sandbox ada (N7)."""
    try:
        from mufakat.sandbox.docker import docker_available as _core_available

        return bool(_core_available())
    except ImportError:
        return _daemon_available_locally()


def build_image(dockerfile: str = "docker/sandbox.Dockerfile") -> bool:
    """Build image sandbox; False bila Docker tidak ada / build gagal."""
    try:
        from mufakat.sandbox.docker import build_image as _build

        return _build(dockerfile)
    except ImportError:
        return False


def run_in_sandbox(image, workdir, command, timeout: int = 300,
                   network_none: bool = True) -> dict:
    """Jalankan ``command`` di container; kembalikan dict hasil.

    Selalu kembalikan ``{"exit_code", "stdout", "stderr", "verified"}``;
    ``verified=False`` bila Docker tidak tersedia (hasil bukan dari
    container sungguhan).
    """
    if not docker_available():
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": "docker tidak tersedia di host ini (binary tidak ada, "
                      "daemon tidak merespons `docker info`, atau image "
                      "mufakat-sandbox belum di-build) — sandbox belum terverifikasi.",
            "verified": False,
        }
    try:
        from mufakat.sandbox.docker import run_in_sandbox as _run

        result = _run(image, workdir, command, timeout=timeout, network_none=network_none)
        if not isinstance(result, dict):
            raise ValueError("run_in_sandbox mengembalikan tipe tak dikenal.")
        result["verified"] = result.get("exit_code") != 127
        return result
    except ImportError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": "Modul sandbox mufakat tidak terpasang — sandbox belum terverifikasi.",
            "verified": False,
        }
    except Exception as exc:  # noqa: BLE001 - jangan pura-pura terverifikasi
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"sandbox gagal dijalankan: {exc}",
            "verified": False,
        }
