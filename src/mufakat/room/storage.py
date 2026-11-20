"""Penyimpanan Room: SQLite (padanan Dexie/IndexedDB di browser) + ekspor.

Browser memakai Dexie (IndexedDB) untuk runs/messages/gateResults/usage;
sisi Python memakai SQLite stdlib (tanpa dependensi baru) dengan tabel
yang sama maknanya, plus ekspor transkrip Markdown. Data disimpan lokal;
tidak ada server eksternal.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

__all__ = ["RoomStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY,
    idea TEXT NOT NULL,
    providers TEXT NOT NULL,
    state TEXT NOT NULL,
    round_no INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    round_no INTEGER NOT NULL,
    phase TEXT NOT NULL,
    source TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    parsed_json TEXT
);
CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    site TEXT NOT NULL,
    day TEXT NOT NULL,
    prompts_copied INTEGER NOT NULL DEFAULT 0
);
"""


class RoomStore:
    """Store SQLite untuk Room: rooms, responses (user imported), usage."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def save_room(self, room) -> None:
        """Simpan/upsert metadata room (objek :class:`mufakat.room.handoff.Room`)."""
        self._conn.execute(
            "INSERT INTO rooms(room_id, idea, providers, state, round_no)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(room_id) DO UPDATE SET"
            " idea=excluded.idea, providers=excluded.providers,"
            " state=excluded.state, round_no=excluded.round_no",
            (
                room.room_id,
                room.idea,
                json.dumps(room.providers, ensure_ascii=False),
                room.state,
                room.round_no,
            ),
        )
        self._conn.commit()

    def save_response(self, room_id: str, record: dict) -> int:
        """Simpan satu respons impor; kembalikan id baris."""
        cursor = self._conn.execute(
            "INSERT INTO responses(room_id, provider, round_no, phase, source,"
            " imported_at, raw_text, parse_status, parsed_json)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                room_id,
                record["provider"],
                record["round"],
                record.get("phase", "proposal"),
                record.get("source", "user imported"),
                record.get("imported_at", ""),
                record.get("raw_text", ""),
                record.get("parse_status", "unparsed"),
                json.dumps(record.get("parsed"), ensure_ascii=False)
                if record.get("parsed") is not None else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def record_usage(self, room_id: str, site: str, day: str) -> None:
        """Naikkan hitungan prompt yang disalin untuk (room, site, hari)."""
        row = self._conn.execute(
            "SELECT id, prompts_copied FROM usage"
            " WHERE room_id=? AND site=? AND day=?",
            (room_id, site, day),
        ).fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO usage(room_id, site, day, prompts_copied)"
                " VALUES(?,?,?,1)",
                (room_id, site, day),
            )
        else:
            self._conn.execute(
                "UPDATE usage SET prompts_copied=? WHERE id=?",
                (row[1] + 1, row[0]),
            )
        self._conn.commit()

    def usage_today(self, room_id: str, site: str, day: str) -> int:
        row = self._conn.execute(
            "SELECT prompts_copied FROM usage WHERE room_id=? AND site=? AND day=?",
            (room_id, site, day),
        ).fetchone()
        return int(row[0]) if row else 0

    def list_responses(self, room_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT provider, round_no, phase, source, imported_at, parse_status"
            " FROM responses WHERE room_id=? ORDER BY id",
            (room_id,),
        ).fetchall()
        return [
            {
                "provider": r[0],
                "round": r[1],
                "phase": r[2],
                "source": r[3],
                "imported_at": r[4],
                "parse_status": r[5],
            }
            for r in rows
        ]

    def export_markdown(self, room_id: str) -> str:
        """Ekspor transkrip room ke Markdown (per ronde, tanpa rahasia)."""
        room_row = self._conn.execute(
            "SELECT idea, state, round_no FROM rooms WHERE room_id=?", (room_id,)
        ).fetchone()
        if room_row is None:
            raise ValueError(f"Room tidak ditemukan: {room_id!r}")
        lines = [f"# Room {room_id}", "", f"Ide: {room_row[0]}",
                 f"State: {room_row[1]} | Ronde: {room_row[2]}", ""]
        rows = self._conn.execute(
            "SELECT provider, round_no, phase, source, imported_at, raw_text,"
            " parse_status FROM responses WHERE room_id=? ORDER BY id",
            (room_id,),
        ).fetchall()
        for provider, round_no, phase, source, imported_at, raw, status in rows:
            lines += [
                f"## Ronde {round_no} — {provider} ({phase})",
                f"Sumber: {source} | Diimpor: {imported_at} | Parse: {status}",
                "",
                raw,
                "",
            ]
        return "\n".join(lines)
