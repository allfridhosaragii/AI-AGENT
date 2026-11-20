"""Parser jawaban AI MUFAKAT Room (Claude §3, §T5).

Setiap prompt diakhiri instruksi: tulis penjelasan singkat, lalu akhiri
dengan SATU blok ```` ```json ```` sesuai skema. Parser mengambil blok
`````json`` terakhir, memvalidasinya, dan mengembalikan status:

- ``ok`` — blok ditemukan dan valid.
- ``repair_needed`` — blok ada tapi rusak/tidak valid; boleh dibuatkan
  SATU prompt perbaikan format (maksimal 1x).
- ``unparsed`` — tidak ada blok JSON sama sekali, atau repair sudah
  dipakai 1x dan masih gagal; jawaban ditampilkan ke pengguna untuk
  diisi manual.

Parser ini TIDAK pernah mengeksekusi isi jawaban: output AI adalah
data tidak tepercaya (V3 Addendum E5).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

__all__ = ["ParseResult", "extract_last_json_block", "parse_reply", "format_repair_prompt"]

ALLOWED_PHASES = {
    "proposal",
    "critique",
    "meeting",
    "spec",
    "code",
    "review",
    "audit",
    "test",
    "revise",
    "rebuttal",
}

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ParseResult:
    """Hasil parse satu jawaban AI."""

    status: str  # "ok" | "repair_needed" | "unparsed"
    payload: dict | None = None
    error: str = ""
    repair_attempted: bool = False


def extract_last_json_block(text: str) -> str | None:
    """Ambil isi blok ```json TERAKHIR dari ``text`` (None bila tak ada)."""
    matches = _JSON_BLOCK_RE.findall(text or "")
    return matches[-1].strip() if matches else None


def _validate(payload: object) -> str:
    """Validasi minimal skema §3; kembalikan pesan error atau '' bila valid."""
    if not isinstance(payload, dict):
        return "Blok JSON bukan object."
    phase = payload.get("phase")
    if phase is not None and phase not in ALLOWED_PHASES:
        return f"phase tidak dikenal: {phase!r}."
    summary = payload.get("summary")
    if summary is not None and not isinstance(summary, str):
        return "summary harus string."
    if summary is not None and len(summary) > 1200:
        return "summary lebih dari 1200 karakter."
    return ""


def parse_reply(text: str, repair_attempted: bool = False) -> ParseResult:
    """Parse jawaban AI menjadi :class:`ParseResult`."""
    block = extract_last_json_block(text)
    if block is None:
        return ParseResult(
            status="unparsed",
            error="Tidak ada blok ```json dalam jawaban.",
            repair_attempted=repair_attempted,
        )
    try:
        payload = json.loads(block)
    except json.JSONDecodeError as exc:
        if repair_attempted:
            return ParseResult(
                status="unparsed",
                error=f"JSON rusak dan repair sudah dipakai 1x: {exc}",
                repair_attempted=True,
            )
        return ParseResult(
            status="repair_needed",
            error=f"JSON rusak: {exc}",
            repair_attempted=repair_attempted,
        )
    error = _validate(payload)
    if error:
        if repair_attempted:
            return ParseResult(status="unparsed", error=error, repair_attempted=True)
        return ParseResult(status="repair_needed", error=error, repair_attempted=repair_attempted)
    return ParseResult(status="ok", payload=payload, repair_attempted=repair_attempted)


def format_repair_prompt(error: str) -> str:
    """Prompt perbaikan format — singkat, hanya soal format (maks 1x pakai)."""
    return (
        "Jawabanmu sebelumnya tidak bisa diparse karena format JSON-nya bermasalah "
        f"({error}). Tolong kirim ulang HANYA blok ```json yang valid sesuai skema, "
        "tanpa mengubah isi usulanmu. Tulis penjelasan singkat, lalu akhiri dengan "
        "SATU blok ```json sesuai skema."
    )
