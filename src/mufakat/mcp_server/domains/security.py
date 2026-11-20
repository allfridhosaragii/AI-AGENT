"""Domain security — pemindaian keamanan (SAST, secret, dependency).

Permission: ``read``/``execute-approved``. Tool ini menjalankan
gate yang tersedia di mesin ini (semgrep/bandit/gitleaks/trivy
atau fallback regex deterministik bila binary tidak ada — lihat
``mufakat.gates``). Bila binary tidak tersedia, hasilnya ditandai
``tool_missing: true`` dan TIDAK diklaim lolos.
"""

from __future__ import annotations

import json
import shutil

from mufakat.mcp_server.tools import err, ok
from mufakat.runner import runs_dir

DOMAIN = "security"

CONTRACTS = [
    {"name": "security_scan", "description": "Status pemindai keamanan yang tersedia.",
     "permission": "read", "scope": "security"},
    {"name": "security_scan_secrets", "description": "Pindai secret (gitleaks/fallback).",
     "permission": "execute-approved", "scope": "security"},
    {"name": "security_scan_dependencies", "description": "Pindai dependency (trivy).",
     "permission": "execute-approved", "scope": "security"},
    {"name": "security_get_findings", "description": "Baca temuan security satu run.",
     "permission": "read", "scope": "security"},
]

_SCANNERS = ("semgrep", "bandit", "gitleaks", "trivy", "ruff")


def security_scan(target: str = ".") -> dict:
    """Status pemindai keamanan yang tersedia (tidak menjalankan scan otomatis)."""
    available = {name: shutil.which(name) is not None for name in _SCANNERS}
    return ok(target=target, scanners_available=available, status="pending",
              note="Scan tidak dijalankan otomatis dari tool ini; pakai "
                   "security_scan_secrets / security_scan_dependencies, "
                   "atau jalankan pemindai secara eksplisit dan simpan "
                   "hasilnya di runs/<run_id>/gates/.")


def _gate_to_dict(result) -> dict:
    return {"tool": result.tool, "passed": bool(result.passed),
            "findings": list(getattr(result, "findings", []) or [])}


def security_scan_secrets(target: str = ".") -> dict:
    """Pindai secret dengan gate gitleaks (fallback regex bila binary hilang)."""
    from mufakat.gates.gitleaks import run

    result = run(target)
    return ok(target=target, tool_missing=shutil.which("gitleaks") is None,
              **_gate_to_dict(result))


def security_scan_dependencies(target: str = ".") -> dict:
    """Pindai dependency dengan gate trivy (belum terverifikasi bila binary hilang)."""
    from mufakat.gates.trivy import run

    result = run(target)
    return ok(target=target, tool_missing=shutil.which("trivy") is None,
              **_gate_to_dict(result))


def security_get_findings(run_id: str) -> dict:
    """Baca temuan security satu run dari runs/<run_id>/gates/."""
    gates_dir = runs_dir() / run_id / "gates"
    if not gates_dir.is_dir():
        return err("Tidak ada hasil gate untuk run ini.", run_id=run_id)
    findings: list[dict] = []
    for child in sorted(gates_dir.iterdir()):
        if child.is_file() and child.suffix == ".json":
            try:
                data = json.loads(child.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            tool = str(data.get("tool", child.stem))
            if tool in ("semgrep", "bandit", "gitleaks", "trivy"):
                findings.extend(data.get("findings", []) or [])
    return ok(run_id=run_id, count=len(findings), findings=findings)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain security ke ``mcp``."""
    for fn in (security_scan, security_scan_secrets,
               security_scan_dependencies, security_get_findings):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
