"""Gates Local Runner (Claude §5, §T12).

Reuse penuh: gate dijalankan oleh :mod:`mufakat.gates.runner` dan
dinilai :mod:`mufakat.gates.verdict` (satu sumber kebenaran — tidak ada
duplikasi logika gate di runner). Modul ini hanya membungkus hasilnya
menjadi dict JSON-serializable untuk native messaging / MCP.
"""

from __future__ import annotations

__all__ = ["run_gates"]


def run_gates(target_dir, profile: str = "python") -> list[dict]:
    """Jalankan semua gate atas ``target_dir``; kembalikan list dict.

    ``profile`` saat ini hanya dicatat (``python``/``node``) — gate yang
    dijalankan adalah gate MUFAKAT yang sudah ada (pytest, ruff, mypy,
    bandit, semgrep, gitleaks, trivy). Gate yang binary-nya tidak ada
    memakai fallback yang sama seperti di MUFAKAT inti (lihat
    ``mufakat/gates/``) dan TIDAK PERNAH pura-pura lolos.
    """
    from mufakat.gates.runner import run_all

    results = run_all(target_dir)
    return [
        {
            "tool": str(result.tool),
            "passed": bool(result.passed),
            "findings": list(result.findings),
            "profile": profile,
        }
        for result in results
    ]
