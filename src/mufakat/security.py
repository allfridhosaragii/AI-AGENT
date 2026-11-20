"""Pengamanan MUFAKAT: redaksi rahasia, larangan perintah, dan larangan otomasi web chat.

Modul ini mandiri — tidak bergantung pada modul MUFAKAT lain — agar bisa
dipakai oleh adapter, CLI, maupun server MCP tanpa import melingkar.
"""

from __future__ import annotations

import re

__all__ = [
    "redact_secrets",
    "is_forbidden_command",
    "check_no_webchat_automation",
]

# Pola rahasia yang umum bocor di log / prompt / output.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # AWS access key id, mis. AKIAIOSFODNN7EXAMPLE
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Bearer token pada header Authorization.
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/=]+"), "Bearer [REDACTED]"),
    # Pasangan kunci=nilai untuk api_key / apikey / secret / password / token.
    (
        re.compile(
            r"(?i)(api[_-]?key|apikey|secret|password|passwd|token)"
            r"(\s*[:=]\s*)([\"']?)[^\s\"',;]+",
        ),
        r"\1\2[REDACTED]",
    ),
]

# Perintah / pola yang dilarang dijalankan atau diteruskan ke shell.
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "--dangerously-skip-permissions",
    "chatgpt.com",
    "claude.ai",
    "~/.codex",
    "~/.claude",
    ".codex",
    ".claude",
    "credential",
)

# Kata kunci yang menandakan permintaan otomasi web chat (ChatGPT/Claude web).
_WEBCHAT_AUTOMATION_KEYWORDS: tuple[str, ...] = (
    "otomasi web chat",
    "otomatisasi web chat",
    "automate chatgpt",
    "automate claude",
    "otomasi chatgpt",
    "otomasi claude",
    "otomatisasi chatgpt",
    "otomatisasi claude",
    "web chat automation",
    "otomasi browser chatgpt",
    "otomasi browser claude",
)


def redact_secrets(text: str) -> str:
    """Ganti pola rahasia pada ``text`` dengan penanda ``[REDACTED]``.

    Menangani AWS access key (``AKIA...``), token ``Bearer``, serta
    pasangan ``api_key`` / ``secret`` / ``password`` / ``token``.
    Teks tanpa rahasia dikembalikan apa adanya.
    """
    redacted = text
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def is_forbidden_command(cmd: str) -> bool:
    """Kembalikan ``True`` bila ``cmd`` mengandung pola yang dilarang.

    Ditolak antara lain: ``--dangerously-skip-permissions``, akses ke
    ``chatgpt.com`` / ``claude.ai``, serta pembacaan direktori kredensial
    seperti ``~/.codex``, ``~/.claude``, atau jalur ``*credential*``.
    """
    lowered = cmd.lower()
    if "--dangerously-skip-permissions" in lowered:
        return True
    if "chatgpt.com" in lowered or "claude.ai" in lowered:
        return True
    if "~/.codex" in lowered or "~/.claude" in lowered:
        return True
    if ".codex" in lowered or ".claude" in lowered:
        return True
    if "credential" in lowered:
        return True
    # Pola generik: membaca file kredensial di ~/.config
    if ".config" in lowered and "credential" in lowered:
        return True
    return False


def check_no_webchat_automation(text: str) -> None:
    """Lempar ``ValueError`` bila ``text`` menyebut otomasi web chat.

    MUFAKAT tidak mengotomasi antarmuka web ChatGPT/Claude; integrasi
    hanya lewat API resmi atau CLI yang didukung.
    """
    lowered = text.lower()
    for keyword in _WEBCHAT_AUTOMATION_KEYWORDS:
        if keyword in lowered:
            raise ValueError(
                "Otomasi web chat tidak diizinkan: MUFAKAT tidak mengotomasi "
                "antarmuka web ChatGPT/Claude. Gunakan API resmi atau CLI yang didukung."
            )
