"""Store dalam-memori bersama untuk tool MCP MUFAKAT.

Catatan jujur: store ini hidup selama proses server MCP berjalan
(stdio). Ini BUKAN penyimpanan permanen — catatan permanen run
ada di ``runs/<run_id>/`` dan tabel SQLite (lihat
``mufakat.storage.db``). Tool yang butuh persistensi antar-proses
harus menulis ke runs/ atau SQLite, bukan ke store ini.
"""

from __future__ import annotations

from mufakat.message_bus import InMemoryMessageBus

agents: dict[str, dict] = {}
meetings: dict[str, dict] = {}
tasks: dict[str, dict] = {}
projects: dict[str, dict] = {}
memories: dict[str, dict] = {}
approvals: dict[str, dict] = {}
references: dict[str, dict] = {}
reviews: dict[str, dict] = {}
evaluations: dict[str, dict] = {}
bus = InMemoryMessageBus()


def reset() -> None:
    """Kosongkan semua store (dipakai test)."""
    agents.clear()
    meetings.clear()
    tasks.clear()
    projects.clear()
    memories.clear()
    approvals.clear()
    references.clear()
    reviews.clear()
    evaluations.clear()
    global bus
    bus = InMemoryMessageBus()
