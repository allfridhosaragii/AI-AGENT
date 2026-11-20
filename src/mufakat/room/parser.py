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

VALID_DECISIONS = ("approve", "revise", "reject")

# Satu fence: ``` + bahasa opsional + isi + ``` penutup. Bahasa ditangkap
# agar fence ```python / ```bash / bare fence sesudah blok json tidak
# salah diambil sebagai blok JSON (dulu regex lama mengambil fence
# polos apa pun sebagai kandidat JSON terakhir).
_FENCE_RE = re.compile(
    r"```[ \t]*([A-Za-z0-9_+\-]*)[ \t]*(?:\n| )?(.*?)```",
    re.DOTALL,
)


@dataclass(frozen=True)
class ParseResult:
    """Hasil parse satu jawaban AI."""

    status: str  # "ok" | "repair_needed" | "unparsed"
    payload: dict | None = None
    error: str = ""
    repair_attempted: bool = False


def _fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Semua fence ```` ``` ```` sebagai (bahasa, isi); bahasa dinormalisasi kecil."""
    blocks: list[tuple[str, str]] = []
    for match in _FENCE_RE.finditer(text or ""):
        lang = (match.group(1) or "").strip().lower()
        content = match.group(2) or ""
        blocks.append((lang, content.strip()))
    return blocks


def extract_last_json_block(text: str) -> str | None:
    """Ambil isi blok ```json TERAKHIR dari ``text`` (None bila tak ada).

    Prioritas: blok berlabel ``json`` terakhir; bila tidak ada, blok
    fence polos (tanpa bahasa) terakhir. Fence berlabel lain
    (``python``, ``bash``, ...) tidak pernah dianggap blok JSON.
    Mendukung blok satu baris (`` ```json {...} ``` ``) dan spasi
    sesudah fence (`` ``` json ``) yang dulu gagal dikenali.
    """
    blocks = _fenced_blocks(text or "")
    json_blocks = [content for lang, content in blocks if lang == "json"]
    if json_blocks:
        return json_blocks[-1]
    bare_blocks = [content for lang, content in blocks if lang == ""]
    return bare_blocks[-1] if bare_blocks else None


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
    vote = payload.get("vote")
    if vote is not None:
        if not isinstance(vote, dict):
            return "vote harus object."
        decision = vote.get("decision")
        if decision is not None and decision not in VALID_DECISIONS:
            return f"vote.decision tidak dikenal: {decision!r}."
        ranking = vote.get("ranking")
        if ranking is not None and (
            not isinstance(ranking, list)
            or any(not isinstance(c, str) for c in ranking)
        ):
            return "vote.ranking harus list string."
    critiques = payload.get("critiques")
    if critiques is not None and not isinstance(critiques, list):
        return "critiques harus list."
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
    if not block:
        if repair_attempted:
            return ParseResult(
                status="unparsed",
                error="Blok ```json kosong dan repair sudah dipakai 1x.",
                repair_attempted=True,
            )
        return ParseResult(
            status="repair_needed",
            error="Blok ```json kosong.",
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
