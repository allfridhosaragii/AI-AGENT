"""Docker sandbox MUFAKAT (T9, diperbaiki audit 20 Nov 2026: H7 + C1;
putaran 2: N1 + N7).

``build_image`` mengembalikan False (tanpa raise) bila binary docker
tidak ada atau build gagal. ``run_in_sandbox`` menjalankan perintah
di container terisolasi dan TIDAK PERNAH fallback ke host:

- user ``10001:10001`` (user ``mufakat`` yang dibuat Dockerfile),
- ``workdir`` selalu absolut (``Path.resolve()`` — path relatif dulu
  dianggap named volume oleh Docker),
- ``--name mufakat-<uuid>`` + ``docker kill`` saat timeout, supaya
  container tidak terus jalan setelah klien mati,
- ``--cap-drop ALL``, ``--security-opt no-new-privileges``,
  ``--pids-limit 256``, ``--read-only --tmpfs /tmp --tmpfs /home/mufakat``
  (N1: ``--read-only`` membuat ``$HOME`` tak bisa ditulis semgrep;
  ``/home/mufakat`` sebagai tmpfs membuat HOME bisa ditulis tanpa
  mengorbankan read-only rootfs),
- mount kode read-only saat ``read_only=True`` (gate baca-saja:
  semgrep/bandit/gitleaks/trivy/lint),
- mount tambahan di luar worktree lewat ``extra_volumes`` (N4:
  artefak gate seperti ``coverage.json`` ditulis ke ``/out``, bukan
  ke worktree — hasil gate tidak boleh dipalsukan / ikut ter-commit).

Deteksi Docker (N7): ``docker_available()`` BUKAN lagi sekadar
``shutil.which("docker")``. Binary tanpa daemon (mis. Docker Desktop
belum dibuka) dulu dilaporkan "tersedia", lalu gate lain lolos kosong
(N1) dan test inti gagal dengan pesan membingungkan. Sekarang:

- ``docker_daemon_available()``: binary ada DAN ``docker info``
  berhasil (timeout 5 detik).
- ``docker_image_available(image)``: ``docker image inspect <image>``
  berhasil (timeout 5 detik).
- ``docker_available()``: True HANYA bila daemon hidup DAN image
  sandbox ada. Gagal -> pemanggil (gate) mengembalikan
  ``BELUM_TERVERIFIKASI``, bukan AMAN.

Bila Docker tidak ada / daemon mati, kembalikan ``exit_code=127`` +
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

# Timeout deteksi daemon/image (N7): cukup untuk daemon lokal yang
# hidup, cukup singkat agar gate fail-closed tanpa menunggu lama.
_DOCKER_PROBE_TIMEOUT = 5


def _probe_ok(args: list[str], timeout: int = _DOCKER_PROBE_TIMEOUT) -> bool:
    """True bila perintah docker selesai dengan exit code 0."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def docker_daemon_available(timeout: int = _DOCKER_PROBE_TIMEOUT) -> bool:
    """True bila binary ``docker`` ada DAN daemon merespons ``docker info``.

    Binary saja TIDAK cukup (N7): CLI Docker tanpa daemon yang hidup
    dulu dilaporkan tersedia, lalu gate lolos kosong.
    """
    if shutil.which("docker") is None:
        return False
    return _probe_ok(["docker", "info"], timeout=timeout)


def docker_image_available(image: str = SANDBOX_IMAGE,
                           timeout: int = _DOCKER_PROBE_TIMEOUT) -> bool:
    """True bila image ``image`` ada di daemon lokal (``docker image inspect``)."""
    if shutil.which("docker") is None:
        return False
    return _probe_ok(["docker", "image", "inspect", str(image)],
                     timeout=timeout)


def docker_available() -> bool:
    """True HANYA bila daemon Docker hidup DAN image sandbox ada (N7).

    Dipakai gate & test sebagai satu-satunya penanda "Docker tersedia":
    gagal di salah satu sisi -> gate mengembalikan
    ``BELUM_TERVERIFIKASI`` (fail-closed), bukan AMAN.
    """
    return (docker_daemon_available()
            and docker_image_available(SANDBOX_IMAGE))


def build_image(dockerfile: str = "docker/sandbox.Dockerfile") -> bool:
    """Build image sandbox; False bila docker tidak ada / build gagal.

    Sengaja memakai ``docker_daemon_available()`` (bukan
    ``docker_available()``): image yang hendak di-build belum ada,
    jadi pengecekan image di sini akan selalu menolak (chicken-egg).
    """
    if not docker_daemon_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "build", "-t", SANDBOX_IMAGE, "-f", dockerfile, "."],
            capture_output=True, text=True, timeout=600,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return False


def run_in_sandbox(image, workdir, command, timeout=300,
                   network_none=True, read_only=False,
                   extra_volumes=None) -> dict:
    """Jalankan ``command`` di container; kembalikan dict hasil.

    Selalu kembalikan ``{"exit_code": int, "stdout": str, "stderr": str,
    "sandbox_unavailable": bool}``; tidak pernah raise untuk docker
    yang hilang / timeout. TIDAK PERNAH menjalankan perintah di host.

    ``extra_volumes``: daftar mount tambahan di luar worktree, tiap
    item ``(host_path, container_path)`` atau string
    ``"host:container"`` (N4: artefak gate ditulis ke mount terpisah).
    """
    if not docker_daemon_available():
        return {"exit_code": 127, "stdout": "",
                "stderr": "Docker tidak tersedia: binary tidak ada atau "
                          "daemon tidak merespons `docker info` "
                          "(periksa Docker Desktop / dockerd).",
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
        # N1: rootfs read-only, tapi $HOME harus bisa ditulis semgrep
        # (cache/settings di ~/.semgrep) -> tmpfs khusus untuk home.
        "--read-only", "--tmpfs", "/tmp", "--tmpfs", "/home/mufakat",
        "-v", mount,
        "-w", "/work",
    ]
    for volume in extra_volumes or []:
        if isinstance(volume, (list, tuple)):
            host_path, container_path = str(volume[0]), str(volume[1])
            spec = f"{host_path}:{container_path}"
        else:
            spec = str(volume)
        cmd += ["-v", spec]
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
