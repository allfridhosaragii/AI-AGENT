"""Docker sandbox MUFAKAT (T9).

``build_image`` mengembalikan False (tanpa raise) bila binary docker
tidak ada atau build gagal. ``run_in_sandbox`` menjalankan perintah
di container terisolasi: user non-root, CPU 1, memori 512 MB, tanpa
jaringan bila ``network_none=True``. Perintah destruktif diblokir
sebelum dijalankan.
"""

from __future__ import annotations

import shutil
import subprocess

_BLOCKED_PATTERNS = (
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){", "shutdown",
    "reboot", "chmod -R 777 /", "> /dev/sd",
)


def _blocked(command: str) -> str | None:
    lowered = command.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            return pattern
    return None


def build_image(dockerfile: str = "docker/sandbox.Dockerfile") -> bool:
    """Build image sandbox; False bila docker tidak ada / build gagal."""
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "build", "-t", "mufakat-sandbox", "-f", dockerfile, "."],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def run_in_sandbox(image, workdir, command, timeout=300,
                   network_none=True) -> dict:
    """Jalankan ``command`` di container; kembalikan dict hasil.

    Selalu kembalikan ``{"exit_code": int, "stdout": str, "stderr": str}``;
    tidak pernah raise untuk docker yang hilang / timeout / perintah
    yang diblokir.
    """
    blocked = _blocked(str(command))
    if blocked:
        return {"exit_code": 1, "stdout": "",
                "stderr": f"Perintah diblokir (pola destruktif: {blocked})."}
    if shutil.which("docker") is None:
        return {"exit_code": 127, "stdout": "",
                "stderr": "docker tidak tersedia di host ini."}
    cmd = [
        "docker", "run", "--rm",
        "--user", "nonroot",
        "--cpus", "1",
        "--memory", "512m",
        "-v", f"{workdir}:/work",
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
                "stderr": result.stderr or ""}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124,
                "stdout": (exc.stdout or b"").decode("utf-8", "replace")
                          if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                "stderr": f"Timeout setelah {timeout} detik."}
    except OSError as exc:
        return {"exit_code": 1, "stdout": "", "stderr": str(exc)}
