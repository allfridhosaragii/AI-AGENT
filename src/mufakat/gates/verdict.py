"""Verdict akhir gates MUFAKAT (T11).

AMAN hanya bila: semua gate passed, coverage >= 0.8 bila ada,
0 HIGH/CRITICAL dari semgrep/bandit, 0 secret, 0 CVE fixable, dan
review approve >= 2/3 bila ada di config.
"""

from __future__ import annotations

DEFAULT_MIN_COVERAGE = 0.8
DEFAULT_MIN_APPROVE_RATIO = 2 / 3


def _finding_category(tool: str, finding: object) -> str:
    # Temuan bisa berupa dict (normal) atau string (dari adapter /
    # gate pihak ketiga) — dulu string membuat .get() melempar
    # AttributeError dan verdict crash.
    if isinstance(finding, dict):
        rule = str(finding.get("rule", "")).lower()
        message = str(finding.get("message", "")).lower()
    else:
        rule, message = "", str(finding).lower()
    text = f"{rule} {message}"
    if tool == "gitleaks" or "secret" in text or "api-key" in text \
            or "password" in text or "token" in text or "private-key" in text:
        return "secret"
    if "sql" in text:
        return "sql-injection"
    if tool == "pytest" or "test" in rule:
        return "test-gagal"
    if tool == "trivy" or "cve" in text:
        return "cve"
    if tool == "lint":
        return "lint"
    if tool in ("semgrep", "bandit"):
        return "keamanan-kode"
    return tool


def _config_value(config, *paths, default=None):
    """Ambil nilai dari config datar atau bersarang (mis. gates.yaml)."""
    if not isinstance(config, dict):
        return default
    for path in paths:
        node = config
        ok = True
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok:
            return node
    return default


def verdict(results, gates_config=None) -> dict:
    """Nilai daftar GateResult -> {safe, status, categories, summary}.

    Status: ``AMAN`` | ``TIDAK AMAN`` | ``BELUM_TERVERIFIKASI``.
    ``BELUM_TERVERIFIKASI`` bila ada gate yang tidak bisa dijalankan
    (sandbox Docker tidak tersedia / tool hilang di sandbox) atau
    tool-nya crash / output-nya tak valid (``tool-error``, N1) — hasil
    itu TIDAK BOLEH dibaca sebagai AMAN (fail-closed, audit H3).
    Coverage dipakai dari hasil terukur gate pytest (``result.coverage``)
    bila ada, else dari config.
    """
    config = gates_config or {}
    safe = True
    unverified = False
    categories: list[str] = []

    def add_category(tool, finding):
        cat = _finding_category(tool, finding)
        if cat not in categories:
            categories.append(cat)

    for result in results:
        tool = getattr(result, "tool", "?")
        passed = getattr(result, "passed", False)
        findings = getattr(result, "findings", []) or []
        if not passed:
            safe = False
        for finding in findings:
            severity = (
                str(finding.get("severity", "")).upper()
                if isinstance(finding, dict) else ""
            )
            rule = str(finding.get("rule", "")).lower() if isinstance(finding, dict) else ""
            if rule in ("sandbox-unavailable", "tool-missing", "tool-error"):
                unverified = True
                if "belum-terverifikasi" not in categories:
                    categories.append("belum-terverifikasi")
            if tool in ("semgrep", "bandit") and severity in ("HIGH", "CRITICAL"):
                safe = False
            if tool == "gitleaks":
                safe = False
            if tool == "trivy" and severity in ("HIGH", "CRITICAL"):
                safe = False
            if severity in ("HIGH", "CRITICAL"):
                add_category(tool, finding)
            elif not passed:
                add_category(tool, finding)

    # Coverage: utamakan hasil TERUKUR dari gate pytest, bukan config.
    measured = _config_value(config, ("coverage",), default=None)
    if measured is None:
        for result in results:
            cov = getattr(result, "coverage", None)
            if cov is not None:
                measured = cov
                break
    # Coverage (bila ada di config): nilai terukur vs batas minimum.
    min_coverage = _config_value(
        config, ("min_coverage",), ("gates", "tests", "min_coverage"),
        default=DEFAULT_MIN_COVERAGE)
    if measured is not None:
        try:
            if float(measured) < float(min_coverage):
                safe = False
                if "coverage" not in categories:
                    categories.append("coverage")
        except (TypeError, ValueError):
            pass

    # Review approve >= 2/3 (bila ada di config).
    approvals = _config_value(config, ("review_approvals",),
                              ("review", "approvals"), default=None)
    total = _config_value(config, ("review_total",),
                          ("review", "total"), default=None)
    min_ratio = _config_value(
        config, ("min_approve_ratio",),
        ("gates", "review", "min_approve_ratio"),
        ("review", "min_approve_ratio"),
        default=DEFAULT_MIN_APPROVE_RATIO)
    if approvals is not None and total:
        try:
            if (float(approvals) / float(total)) < float(min_ratio):
                safe = False
                if "review" not in categories:
                    categories.append("review")
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    failed_tools = sorted({getattr(r, "tool", "?") for r in results
                           if not getattr(r, "passed", False)})
    total_findings = sum(len(getattr(r, "findings", []) or []) for r in results)
    if unverified:
        summary = ("Belum terverifikasi: sandbox Docker / tool gate tidak "
                   f"tersedia ({', '.join(failed_tools) or 'tidak ada'}); "
                   "hasil ini bukan AMAN.")
        status = "BELUM_TERVERIFIKASI"
    elif safe:
        summary = ("Semua gate lolos; tidak ada temuan HIGH/CRITICAL, "
                   "secret, atau CVE fixable.")
        status = "AMAN"
    else:
        summary = (f"Tidak aman: {len(failed_tools)} gate gagal "
                   f"({', '.join(failed_tools) or 'tidak ada'}), "
                   f"{total_findings} temuan, kategori: "
                   f"{', '.join(sorted(categories)) or 'tidak ada'}.")
        status = "TIDAK AMAN"
    return {"safe": safe, "status": status,
            "categories": sorted(categories), "summary": summary}
