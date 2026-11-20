"""Pemindai regex bersama untuk gate fallback (T10).

Dipakai bila binary asli (semgrep/bandit/gitleaks) tidak tersedia.
Deterministik: file diurutkan, pola dicocokkan per baris.
"""

from __future__ import annotations

import re
from pathlib import Path

_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
              ".tox", ".pytest_cache", "runs", "dist", "build", ".eggs"}


def iter_text_files(target_dir, extensions=None):
    """Yield file teks di bawah ``target_dir`` (urut, tanpa dir skip)."""
    root = Path(target_dir)
    if root.is_file():
        yield root
        return
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        files.append(path)
    for path in sorted(files):
        yield path


def read_lines(path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def scan_patterns(target_dir, patterns, extensions=None):
    """Cocokkan ``patterns`` [(rule, severity, regex, message)] per baris.

    Kembalikan daftar finding dict {severity, file, line, rule, message}.
    Satu finding per (file, line, rule).
    """
    compiled = [(rule, sev, re.compile(rx), msg)
                for rule, sev, rx, msg in patterns]
    findings, seen = [], set()
    for path in iter_text_files(target_dir, extensions):
        try:
            rel = str(path.relative_to(Path(target_dir)))
        except ValueError:
            rel = str(path)
        for lineno, line in enumerate(read_lines(path), start=1):
            for rule, severity, rx, message in compiled:
                if rx.search(line):
                    key = (rel, lineno, rule)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "severity": severity, "file": rel, "line": lineno,
                        "rule": rule, "message": message,
                    })
    return findings
