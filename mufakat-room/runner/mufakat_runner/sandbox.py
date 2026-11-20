"""Sandbox Docker Local Runner (Claude §5).

Reuse: bila paket ``mufakat`` terpasang, eksekusi didelegasikan ke
:mod:`mufakat.sandbox.docker` (user non-root, ``--network none`` saat
test, limit CPU/RAM/waktu). Bila Docker tidak tersedia, fungsi mengembalikan
hasil "belum terverifikasi" (exit 127) — TIDAK PERNAH pura-pura jalan.
"""

from __future__ import annotations

import shutil

__all__ = ["docker_available", "run_in_sandbox", "build_image"]


def docker_available() -> bool:
    """True bila binary ``docker`` ada di PATH host ini."""
    return shutil.which("docker") is not None


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
            "stderr": "docker tidak tersedia di host ini — sandbox belum terverifikasi.",
            "verified": False,
        }
    try:
        from mufakat.sandbox.docker import run_in_sandbox as _run

        result = _run(image, workdir, command, timeout=timeout, network_none=network_none)
        result["verified"] = result.get("exit_code") != 127
        return result
    except ImportError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": "Modul sandbox mufakat tidak terpasang — sandbox belum terverifikasi.",
            "verified": False,
        }
