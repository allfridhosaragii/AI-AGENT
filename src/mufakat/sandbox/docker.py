"""Docker sandbox MUFAKAT (T9, diperbaiki audit 20 Nov 2026: H7 + C1).

``build_image`` mengembalikan False (tanpa raise) bila binary docker
tidak ada atau build gagal. ``run_in_sandbox`` menjalankan perintah
di container terisolasi dan TIDAK PERNAH fallback ke host:

- user ``10001:10001`` (user ``mufakat`` yang dibuat Dockerfile),
- ``workdir`` selalu absolut (``Path.resolve()`` — path relatif dulu
  dianggap named volume oleh Docker),
- ``--name mufakat-<uuid>`` + ``docker kill`` saat timeout, supaya
  container tidak terus jalan setelah klien mati,
- ``--cap-drop ALL``, ``--security-opt no-new-privileges``,
  ``--pids-limit 256``, ``--read-only --tmpfs /tmp``,
- mount kode read-only saat ``read_only=True`` (gate baca-saja:
  semgrep/bandit/gitleaks/trivy/lint).

Pertahanan adalah isolasi container — BUKAN blocklist string pola
perintah (blocklist dulu mudah dilewati dan sudah dihapus).
Bila Docker tidak ada, kembalikan ``exit_code=127`` +
``sandbox_unavailable=True``; pemanggil (gate) WAJIB menerjemahkannya
menjadi ``passed=False`` / ``BELUM_TERVERIFIKASI``.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

SANDBOX_IMAGE = "mufakat-sandbox"
SANDBOX_UID_GID = "10001:10001"


def build_image(dockerfile: str = "docker/sandbox.Dockerfile") -> bool:
    """Build image sandbox; False bila docker tidak ada / build gagal."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "build", "-t", SANDBOX_IMAGE, "-f", dockerfile, "."],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def docker_available() -> bool:
    """True bila binary ``docker`` ada di PATH."""
    return shutil.which("docker") is not None


def run_in_sandbox(image, workdir, command, timeout=300,
                   network_none=True, read_only=False) -> dict:
    """Jalankan ``command`` di container; kembalikan dict hasil.

    Selalu kembalikan ``{"exit_code": int, "stdout": str, "stderr": str,
    "sandbox_unavailable": bool}``; tidak pernah raise untuk docker
    yang hilang / timeout. TIDAK PERNAH menjalankan perintah di host.
    """
    if shutil.which("docker") is None:
        return {"exit_code": 127, "stdout": "",
                "stderr": "docker tidak tersedia di host ini.",
                "sandbox_unavailable": True}
    workdir_abs = str(Path(workdir).resolve())
    container = f"mufakat-{uuid.uuid4().hex[:12]}"
    mount = f"{workdir_abs}:/work:ro" if read_only else f"{workdir_abs}:/work"
    cmd = [
        "docker", "run", "--rm",
        "--name", container,
        "--user", SANDBOX_UID_GID,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--cpus", "1",
        "--memory", "512m",
        "--read-only", "--tmpfs", "/tmp",  # nosec B108 - /tmp di sini mount tmpfs container, bukan file temp host
        "-v", mount,
        "-w", "/work",
    ]
    if network_none:
        cmd += ["--network", "none"]
    cmd += [str(image), "sh", "-c", str(command)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout)
        return {"exit_code": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "sandbox_unavailable": False}
    except subprocess.TimeoutExpired as exc:
        # Container tetap jalan bila hanya klien yang mati (H7):
        # bunuh paksa berdasarkan nama unik container.
        try:
            subprocess.run(["docker", "kill", container],
                           capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass
        stdout_text = ""
        if isinstance(exc.stdout, bytes):
            stdout_text = exc.stdout.decode("utf-8", "replace")
        elif isinstance(exc.stdout, str):
            stdout_text = exc.stdout
        return {"exit_code": 124, "stdout": stdout_text,
                "stderr": f"Timeout setelah {timeout} detik; "
                          f"container {container} dimatikan.",
                "sandbox_unavailable": False}
    except OSError as exc:
        return {"exit_code": 1, "stdout": "",
                "stderr": str(exc), "sandbox_unavailable": False}
