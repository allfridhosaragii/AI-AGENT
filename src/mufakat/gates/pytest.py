"""Gate pytest (T10, diperbaiki audit 20 Nov 2026: C1 + H3;
putaran 2: N1 + N4).

Dijalankan HANYA di dalam sandbox Docker via
:mod:`mufakat.gates._sandbox` — TIDAK PERNAH di host. Tanpa Docker:
``passed=False``, ``rule="sandbox-unavailable"``, verdict
``BELUM_TERVERIFIKASI``.

- Tidak ada test -> GAGAL (``no-tests``): kode baru tanpa test
  tidak boleh lolos.
- pytest tidak tersedia di dalam sandbox -> gagal-tertutup
  (``pytest-missing``), bukan AMAN.

N4 — hasil pytest/coverage TIDAK BOLEH dipalsukan kode AI:
- ``coverage.json`` / ``.coverage`` lama di worktree DIHAPUS sebelum
  run (dulu file palsu 100% dari worktree langsung dibaca -> AMAN).
- Coverage ditulis ke mount TERPISAH di luar worktree
  (``-v <tmpdir>:/out``, ``--cov-report=json:/out/coverage.json``)
  dan dibaca dari mount itu — kode AI di worktree (read-write)
  tidak bisa menimpa hasil yang dibaca gate.
- Dijalankan dengan ``-p no:cacheprovider -o addopts=""``: tidak ada
  ``.pytest_cache`` di worktree dan ``conftest.py``/``pytest.ini``
  AI tidak bisa mematikan plugin cov lewat ``addopts``.
- Perubahan ``conftest.py`` / ``pytest.ini`` / ``pyproject.toml``
  (``[tool.pytest]``) / ``setup.cfg`` / ``tox.ini`` yang belum
  di-commit ke HEAD = temuan blocking (``pytest-config-changed``):
  file konfigurasi pytest hanya dipercaya bila sudah melewati review
  manusia (= ter-commit). Tanpa review, verdict AMAN ditolak walau
  test "lolos" — ``conftest.py`` AI bisa memaksa exit 0 /
  mematikan cov / menimpa coverage.

N1 — exit code: 0 lolos, 1 test gagal, 2 interupsi, 5 tidak ada test
terkumpul; 3 (internal error) / 4 (usage error) / lainnya ->
``tool-error`` (bukan "test gagal").
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from ._sandbox import run_gate_in_sandbox, tool_error
    from .runner import GateResult
except ImportError:  # pragma: no cover
    from mufakat.gates._sandbox import run_gate_in_sandbox, tool_error  # type: ignore
    from mufakat.gates.runner import GateResult  # type: ignore

# File konfigurasi pytest yang perubahannya tanpa review = blocking.
_CONFIG_FILES = ("conftest.py", "pytest.ini", "pyproject.toml",
                 "setup.cfg", "tox.ini")

# File konfigurasi yang hanya relevan bila benar-benar memuat
# konfigurasi pytest (pyproject.toml tanpa [tool.pytest] tidak dihitung).
_PYTEST_CONFIG_SECTION = {
    "pyproject.toml": re.compile(r"^\s*\[\s*tool\.pytest(\.ini_options)?\s*\]",
                                re.MULTILINE),
    "setup.cfg": re.compile(r"^\s*\[\s*tool:pytest\s*\]", re.MULTILINE),
    "tox.ini": re.compile(r"^\s*\[\s*pytest\s*\]", re.MULTILINE),
}


def _has_tests(target_dir) -> bool:
    root = Path(target_dir)
    if root.is_file():
        return root.name.startswith("test_") or root.name.endswith("_test.py")
    for path in root.rglob("*.py"):
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            return True
    return False


def _read_coverage_file(coverage_path) -> float | None:
    """Baca persen coverage dari ``coverage.json`` di mount luar worktree."""
    try:
        data = json.loads(Path(coverage_path).read_text(encoding="utf-8"))
        total = data.get("totals", {}).get("percent_covered")
        return float(total) / 100.0 if total is not None else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _file_has_pytest_config(path: Path) -> bool:
    """True bila file konfigurasi ini benar-benar memuat config pytest."""
    pattern = _PYTEST_CONFIG_SECTION.get(path.name)
    if pattern is None:
        return True  # conftest.py / pytest.ini selalu relevan.
    try:
        return pattern.search(path.read_text(encoding="utf-8")) is not None
    except (OSError, ValueError):
        return False


def _pytest_config_changed(target_dir) -> list[str]:
    """Daftar file konfigurasi pytest yang berubah/belum di-commit.

    Aturan (N4): file konfigurasi pytest hanya dipercaya bila sudah
    ter-commit ke HEAD (melewati review manusia). File yang baru
    (untracked) atau berubah vs HEAD -> blocking. Bila target BUKAN
    repo git (``git status`` gagal), provenance tidak bisa dibuktikan:
    file konfigurasi yang ADA di target dianggap belum direview dan
    ikut blocking — kecuali bila target memang tidak memuat file itu.
    """
    root = Path(target_dir)
    if root.is_file():
        return []
    present = [name for name in _CONFIG_FILES
               if (root / name).is_file() and _file_has_pytest_config(root / name)]
    if not present:
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", *present],
            cwd=str(root), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return present
    if result.returncode != 0:
        # Bukan repo git -> provenance tak terbukti (lihat docstring).
        return present
    changed: list[str] = []
    for line in result.stdout.splitlines():
        # Format porcelain: XY <path> (path bisa dikutip bila ada spasi).
        path = line[3:].strip().strip('"') if len(line) > 3 else ""
        if path in present and path not in changed:
            changed.append(path)
    return changed


def run(target_dir, sandbox_runner=None) -> GateResult:
    """Jalankan gate pytest atas ``target_dir`` (di sandbox)."""
    if not _has_tests(target_dir):
        return GateResult(tool="pytest", passed=False, findings=[{
            "severity": "HIGH", "file": "", "line": 0, "rule": "no-tests",
            "message": "Tidak ada test ditemukan — kode tanpa test gagal (fail-closed).",
        }])
    # N4: hapus artefak coverage lama di worktree SEBELUM run — file
    # palsu dari iterasi lalu / yang ditanam AI tidak boleh dibaca.
    root = Path(target_dir)
    for stale in ("coverage.json", ".coverage"):
        try:
            (root / stale).unlink(missing_ok=True)
        except OSError:
            pass
    # N4: coverage ditulis ke mount terpisah di luar worktree.
    # Container jalan sebagai uid 10001, jadi direktori mount harus
    # bisa ditulis user itu (mkdtemp default 0700 milik host user).
    out_host = tempfile.mkdtemp(prefix="mufakat-gate-out-")
    os.chmod(out_host, 0o777)
    try:
        result = run_gate_in_sandbox(
            "pytest", target_dir,
            # COVERAGE_FILE=/out/.coverage: file data coverage juga
            # keluar dari worktree (bukan hanya laporan JSON-nya).
            "COVERAGE_FILE=/out/.coverage python -m pytest -q "
            "-p no:cacheprovider -o addopts=\"\" "
            "--cov=. --cov-report=json:/out/coverage.json .",
            timeout=600, read_only=False, sandbox_runner=sandbox_runner,
            extra_mounts=[(out_host, "/out")])
        if isinstance(result, GateResult):
            return result
        # N4: konfigurasi pytest yang diubah AI tanpa review manusia
        # membuat hasil run ini tidak bisa dipercaya — tolak AMAN
        # walau exit code 0. Cek SETELAH run (sandbox terisolasi, jadi
        # conftest jahat tidak bisa menyentuh host), SEBELUM hasil dibaca.
        changed = _pytest_config_changed(target_dir)
        if changed:
            return GateResult(tool="pytest", passed=False, findings=[{
                "severity": "HIGH", "file": changed[0], "line": 0,
                "rule": "pytest-config-changed",
                "message": "File konfigurasi pytest berubah tanpa review "
                           "manusia (belum di-commit): "
                           + ", ".join(changed) + ". conftest.py / "
                           "pytest.ini / [tool.pytest] bisa memaksa exit 0, "
                           "mematikan coverage, atau memalsukan hasil — "
                           "verdict AMAN ditolak (blocking).",
            }])
        output = (result.get("stdout") or "") + "\n" + (result.get("stderr") or "")
        coverage = _read_coverage_file(Path(out_host) / "coverage.json")
        exit_code = result.get("exit_code")
        if "No module named pytest" in output:
            return GateResult(tool="pytest", passed=False, findings=[{
                "severity": "HIGH", "file": "", "line": 0,
                "rule": "pytest-missing",
                "message": "pytest tidak tersedia di dalam sandbox.",
            }], coverage=coverage)
        if exit_code in (3, 4):
            return tool_error(
                "pytest",
                f"pytest gagal internal (exit code {exit_code}) — hasil "
                "tidak dapat dipercaya, bukan AMAN.")
        if exit_code is not None and exit_code not in (0, 1, 2, 5):
            return tool_error(
                "pytest",
                f"pytest keluar dengan exit code tak dikenal {exit_code} — "
                "hasil tidak dapat dipercaya, bukan AMAN.")
        if exit_code == 0:
            findings = []
            if coverage is not None:
                findings.append({
                    "severity": "INFO", "file": "", "line": 0,
                    "rule": "coverage",
                    "message": f"Coverage terukur: {coverage * 100:.1f}%.",
                })
            return GateResult(tool="pytest", passed=True, findings=findings,
                              coverage=coverage)
        findings = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("FAILED") or "assert" in line and "::" in line:
                findings.append({
                    "severity": "HIGH", "file": "", "line": 0,
                    "rule": "test-failed", "message": line[:300],
                })
        if not findings:
            tail = [ln for ln in output.splitlines() if ln.strip()][-3:]
            findings.append({
                "severity": "HIGH", "file": "", "line": 0,
                "rule": "test-failed",
                "message": "pytest gagal (exit code "
                           f"{exit_code}: " + " | ".join(tail)[:300],
            })
        return GateResult(tool="pytest", passed=False, findings=findings,
                          coverage=coverage)
    finally:
        # N4: artefak coverage tidak boleh tertinggal di worktree
        # (mis. bila tool mengabaikan COVERAGE_FILE) — hapus lagi
        # setelah run, lalu buang mount luar.
        for stale in ("coverage.json", ".coverage"):
            try:
                (root / stale).unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(out_host, ignore_errors=True)
