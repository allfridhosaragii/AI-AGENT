"""Anti-loop MUFAKAT Room (Claude §2.4, §T13).

Eskalasi bila:
- hash (diff + daftar temuan) yang sama muncul 2x, atau
- jumlah temuan tidak turun selama 2 iterasi berturut-turut.

Reuse: logika ini melengkapi ``mufakat.consensus`` / graph anti-loop yang
sudah ada; modul ini versi ringkas khusus Room agar engine TS dan Python
memakai aturan yang sama (hash stabil, batas sama).
"""

from __future__ import annotations

import hashlib
import json

__all__ = ["AntiLoop", "hash_diff_findings"]


def _normalize_diff(diff: str) -> str:
    """Normalisasi diff agar hash stabil: spasi akhir baris dan baris
    kosong di ujung diabaikan (dulu ``"d"`` vs ``"d\\n"`` hash-nya beda
    sehingga loop yang sama tidak terdeteksi)."""
    return "\n".join(line.rstrip() for line in (diff or "").strip().splitlines())


def hash_diff_findings(diff: str, findings: list) -> str:
    """Hash stabil dari diff + temuan (temuan diurutkan dulu).

    Temuan yang tidak bisa di-JSON-kan (mis. ``set``) tidak lagi
    melempar ``TypeError`` — dipakai ``default=str`` seperti pada
    ``mufakat.graph.edges.current_hash``. ``findings=None`` dihitung
    sebagai list kosong.
    """
    findings = findings or []
    try:
        normalized_findings = sorted(
            json.dumps(f, sort_keys=True, ensure_ascii=False, default=str)
            for f in findings
        )
        payload = json.dumps(
            {"diff": _normalize_diff(diff), "findings": normalized_findings},
            sort_keys=True,
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        # Fallback terakhir: repr terurut (tetap deterministik).
        payload = json.dumps(
            {
                "diff": _normalize_diff(diff),
                "findings": sorted(repr(f) for f in findings),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AntiLoop:
    """Pelacak osilasi / stagnasi; ``should_escalate`` memutuskan eskalasi."""

    def __init__(self) -> None:
        self._hash_counts: dict[str, int] = {}
        self._finding_counts: list[int] = []

    def observe(self, diff: str, findings: list) -> dict:
        """Catat satu iterasi; kembalikan status eskalasi iterasi ini."""
        findings = findings or []
        digest = hash_diff_findings(diff, findings)
        self._hash_counts[digest] = self._hash_counts.get(digest, 0) + 1
        self._finding_counts.append(len(findings))
        repeated = self._hash_counts[digest] >= 2
        stagnant = (
            len(self._finding_counts) >= 3
            and self._finding_counts[-1] >= self._finding_counts[-2] >= self._finding_counts[-3]
            and self._finding_counts[-1] > 0
        )
        escalate = repeated or stagnant
        return {
            "hash": digest,
            "hash_seen": self._hash_counts[digest],
            "finding_count": len(findings),
            "repeated_hash": repeated,
            "stagnant_findings": stagnant,
            "escalate": escalate,
        }

    def reset(self) -> None:
        """Kosongkan riwayat (dipakai saat memulai run/ronde baru)."""
        self._hash_counts.clear()
        self._finding_counts.clear()
