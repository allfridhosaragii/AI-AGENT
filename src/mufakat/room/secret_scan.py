"""Secret Scanner MUFAKAT Room (Claude §0.2 / §T8, V3 Addendum E3/E4).

Memindai teks prompt SEBELUM disalin/dikirim ke situs AI. Bila ada
temuan, prompt DIBLOKIR dan pengguna diperingatkan — pemindaian tidak
pernah diam-diam menghapus atau mengubah isi tanpa memberi tahu.

Pola yang dipindai (regex, tanpa pernah menyimpan nilai aslinya ke
log): API key umum, token Bearer, pasangan ``key=``/``password=``,
blok ``-----BEGIN ...-----``, rujukan ``.env``, dan kredensial AWS /
GitHub / Anthropic / OpenAI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["SecretFinding", "scan_text", "contains_secret", "redact_matches"]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]{10,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("env_file_ref", re.compile(r"(?i)\.env\b")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)(api[_-]?key|apikey|secret|password|passwd|token)"
            r"(\s*[:=]\s*)([\"']?)[^\s\"',;]{4,}"
        ),
    ),
    (
        "generic_long_token",
        re.compile(r"(?i)(token|secret)\s*[:=]\s*['\"][A-Za-z0-9\-_]{16,}['\"]"),
    ),
]


@dataclass(frozen=True)
class SecretFinding:
    """Satu temuan secret scanner (nilai asli TIDAK disimpan)."""

    pattern: str
    preview: str  # 4 karakter pertama + "..." — cukup untuk mengenali, bukan bocor.

    def as_dict(self) -> dict[str, str]:
        return {"pattern": self.pattern, "preview": self.preview}


def _preview(match: str) -> str:
    cleaned = match.strip()
    return (cleaned[:4] + "...") if len(cleaned) > 4 else "****"


def scan_text(text: str) -> list[SecretFinding]:
    """Pindai ``text``; kembalikan daftar temuan (kosong = bersih)."""
    findings: list[SecretFinding] = []
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            findings.append(SecretFinding(pattern=name, preview=_preview(match.group(0))))
    return findings


def contains_secret(text: str) -> bool:
    """True bila ada secret yang terdeteksi pada ``text``."""
    return bool(scan_text(text))


def redact_matches(text: str) -> str:
    """Ganti semua kecocokan pola rahasia dengan ``[REDACTED:<pola>]``."""
    redacted = text or ""
    for name, pattern in _PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{name}]", redacted)
    return redacted
