"""Penulis transkrip run MUFAKAT: JSONL + ringkasan Markdown per ronde.

Satu run menempati satu direktori, mis. ``runs/<run_id>/``:

- ``transcript.jsonl`` — satu :class:`MufakatMessage` per baris.
- ``rounds/round-XX.md`` — ringkasan ronde: tabel vote dan kritik per severity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from mufakat.consensus.protocol import MufakatMessage

__all__ = ["TranscriptWriter", "load_transcript"]


class TranscriptWriter:
    """Menulis pesan konsensus ke direktori run."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "rounds").mkdir(parents=True, exist_ok=True)
        self.transcript_path = self.run_dir / "transcript.jsonl"

    def append(self, message: MufakatMessage) -> Path:
        """Tambahkan satu pesan ke ``transcript.jsonl``; kembalikan jalurnya."""
        from mufakat.consensus.protocol import to_jsonl

        with open(self.transcript_path, "a", encoding="utf-8") as fh:
            fh.write(to_jsonl(message) + "\n")
        return self.transcript_path

    def render_round_markdown(
        self, round_no: int, messages: Iterable[MufakatMessage]
    ) -> Path:
        """Tulis ``rounds/round-XX.md`` berisi tabel vote dan kritik per severity.

        Mengembalikan jalur file Markdown yang ditulis.
        """
        msgs = list(messages)
        lines: list[str] = [f"# Ronde {round_no}", ""]
        lines.append("## Vote")
        lines.append("")
        lines.append("| Agent | Peran | Stance | Vote | Ringkasan |")
        lines.append("|---|---|---|---|---|")
        voted = False
        for msg in msgs:
            vote = msg.content.get("vote", "")
            if vote:
                voted = True
                summary = str(msg.content.get("summary", "")).replace("\n", " ")[:120]
                lines.append(
                    f"| {msg.agent_id} | {msg.role.value} | "
                    f"{msg.stance.value if msg.stance else '-'} | {vote} | {summary} |"
                )
        if not voted:
            lines.append("| - | - | - | - | Belum ada vote pada ronde ini. |")
        lines.append("")
        lines.append("## Kritik per Severity")
        lines.append("")
        lines.append("| Agent | Severity | Kritik |")
        lines.append("|---|---|---|")
        found = False
        for msg in msgs:
            critiques = msg.content.get("critiques") or []
            for crit in critiques:
                found = True
                if isinstance(crit, dict):
                    severity = str(crit.get("severity", "-"))
                    text = str(crit.get("text", crit.get("message", ""))).replace("\n", " ")
                else:
                    severity, text = "-", str(crit).replace("\n", " ")
                lines.append(f"| {msg.agent_id} | {severity} | {text} |")
        if not found:
            lines.append("| - | - | Belum ada kritik pada ronde ini. |")
        lines.append("")

        out_path = self.run_dir / "rounds" / f"round-{round_no:02d}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path


def load_transcript(path: str | Path) -> list[MufakatMessage]:
    """Baca ``transcript.jsonl`` dan kembalikan daftar :class:`MufakatMessage`."""
    from mufakat.consensus.protocol import from_jsonl

    transcript = Path(path)
    messages: list[MufakatMessage] = []
    if not transcript.exists():
        return messages
    with open(transcript, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                messages.append(from_jsonl(line))
    return messages
