"""Secret Scanner MUFAKAT Room (Claude §0.2 / §T8, V3 Addendum E3/E4).

Memindai teks prompt SEBELUM disalin/dikirim ke situs AI. Bila ada
temuan, prompt DIBLOKIR dan pengguna diperingatkan — pemindaian tidak
pernah diam-diam menghapus atau mengubah isi tanpa memberi tahu.

Pola yang dipindai (regex, tanpa pernah menyimpan nilai aslinya ke
log): API key umum, token Bearer, pasangan ``key=``/``password=``,
blok ``-----BEGIN ...-----``, rujukan ``.env``, dan kredensial AWS /
GitHub / Anthropic / OpenAI / Google / Slack.

Perbaikan audit 20 Nov 2026: pola yang dulu lolos — ``sk-proj-...``,
``github_pat_...``, ``AIza...`` (Google), ``xoxb-...`` (Slack),
``-----begin ...-----`` huruf kecil, dan ``api key = ...`` (spasi) —
kini terdeteksi. Putaran 2 (N14): ``glpat-...`` (GitLab) dan ``hf_...``
(HuggingFace) ditambahkan untuk paritas dengan TS
(``mufakat-room/src/engine/secretScan.ts``). Temuan ganda pada rentang
yang sama (satu secret yang cocok dua pola) hanya dilaporkan sekali.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["SecretFinding", "scan_text", "contains_secret", "redact_matches"]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("github_fine_grained_token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9\-_]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    # N14 (putaran 2, paritas dengan TS mufakat-room/src/engine/secretScan.ts):
    # GitLab personal access token dan HuggingFace token.
    ("gitlab_token", re.compile(r"glpat-[A-Za-z0-9\-_]{20,}")),
    ("huggingface_token", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]{10,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE)),
    ("env_file_ref", re.compile(r"(?i)\.env\b")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)(api[ _\-]?key|apikey|secret|password|passwd|token|access[ _\-]?key)"
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
    """Pindai ``text``; kembalikan daftar temuan (kosong = bersih).

    Satu rentang teks yang cocok beberapa pola hanya dilaporkan sekali
    (pola pertama yang cocok menang) agar satu secret tidak dihitung
    berkali-kali.
    """
    findings: list[SecretFinding] = []
    seen_spans: list[tuple[int, int]] = []
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            span = (match.start(), match.end())
            # Rentang yang tumpang tindih dengan temuan sebelumnya adalah
            # secret yang sama (mis. sk-... di dalam api_key = "sk-...")
            # — laporkan sekali saja.
            if any(span[0] < end and start < span[1] for start, end in seen_spans):
                continue
            seen_spans.append(span)
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
