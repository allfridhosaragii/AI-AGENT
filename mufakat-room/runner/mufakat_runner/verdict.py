"""Verdict Local Runner (Claude §2.3, §T12).

Reuse :func:`mufakat.gates.verdict.verdict` untuk kriteria AMAN
(semua gate lolos, 0 HIGH/CRITICAL, 0 secret, 0 CVE fixable, coverage
>= 80%). Modul ini menambah status ketiga, ``ESKALASI``, yang dipakai
bila anti-loop memicu eskalasi (hash berulang / temuan stagnan) — dalam
hal itu hasil gates tidak lagi menentukan AMAN/TIDAK AMAN sendirian.
"""

from __future__ import annotations

__all__ = ["apply_verdict"]


def apply_verdict(results, gates_config=None, escalate: bool = False) -> dict:
    """Nilai hasil gate -> ``{safe, status, categories, summary}``.

    ``results``: list dict ``{tool, passed, findings}`` (dari
    :func:`mufakat_runner.gates.run_gates`) atau objek GateResult.
    ``status``: ``AMAN`` | ``TIDAK AMAN`` | ``ESKALASI``.
    """
    from mufakat.gates.verdict import verdict as _verdict

    class _Result:  # adapter duck-typing untuk mufakat.gates.verdict
        def __init__(self, item):
            if isinstance(item, dict):
                self.tool = item.get("tool", "?")
                self.passed = bool(item.get("passed", False))
                self.findings = list(item.get("findings") or [])
            else:
                self.tool = getattr(item, "tool", "?")
                self.passed = bool(getattr(item, "passed", False))
                self.findings = list(getattr(item, "findings", []) or [])

    normalized = [_Result(item) for item in results]
    outcome = _verdict(normalized, gates_config)
    if escalate:
        outcome = dict(outcome)
        outcome["safe"] = False
        outcome["status"] = "ESKALASI"
        outcome["summary"] = (
            "Eskalasi anti-loop: " + outcome.get("summary", "")
        )
    return outcome
