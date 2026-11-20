"""Runner gates MUFAKAT (T10).

``run_all(target_dir)`` menjalankan semua gate dan mengembalikan
``list[GateResult]``. Gate yang modulnya hilang / raise diubah menjadi
GateResult gagal-terbuka (``passed=False`` + finding error) — runner
tidak pernah raise karena satu gate bermasalah.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

_GATE_MODULES = ("semgrep", "bandit", "gitleaks", "trivy", "pytest", "lint")


@dataclass
class GateResult:
    tool: str
    passed: bool
    findings: list[dict] = field(default_factory=list)


def _failed_open(tool: str, message: str) -> GateResult:
    return GateResult(tool=tool, passed=False, findings=[{
        "severity": "HIGH", "file": "", "line": 0,
        "rule": "gate-error", "message": message,
    }])


def run_all(target_dir) -> list[GateResult]:
    """Jalankan semua gate atas ``target_dir``."""
    results = []
    for name in _GATE_MODULES:
        try:
            module = importlib.import_module(f".{name}", __package__)
            run = getattr(module, "run")
        except Exception as exc:  # modul gate hilang / gagal import
            results.append(_failed_open(name, f"Gate {name} tidak dapat dimuat: {exc}"))
            continue
        try:
            result = run(target_dir)
        except Exception as exc:  # gate raise -> gagal-terbuka
            results.append(_failed_open(name, f"Gate {name} gagal: {exc}"))
            continue
        # Duck-typing, bukan isinstance: bila paket `mufakat` terimpor dua
        # kali (mis. via sys.path berbeda), identitas kelas GateResult bisa
        # berbeda antar salinan walau kodenya sama. Terima objek apa pun
        # yang punya atribut tool/passed/findings, lalu normalisasi.
        if not (hasattr(result, "tool") and hasattr(result, "passed")
                and hasattr(result, "findings")):
            results.append(_failed_open(name, f"Gate {name} mengembalikan tipe tak dikenal."))
            continue
        results.append(GateResult(tool=str(result.tool), passed=bool(result.passed),
                                  findings=list(result.findings)))
    return results
