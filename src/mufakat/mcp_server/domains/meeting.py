"""Domain meeting — rapat, ronde debat, rebuttal, revisi, keputusan.

Permission: ``write-sandbox`` untuk membuat/mengisi meeting,
``read`` untuk membaca. Keputusan dicatat bersama dissent bila ada;
meeting TIDAK mengeksekusi kode atau commit apa pun.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, new_id, ok
from mufakat.runner import utcnow

from . import store

DOMAIN = "meeting"

CONTRACTS = [
    {"name": "meeting_create", "description": "Buat meeting (rapat konsensus) baru.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_submit_argument", "description": "Kirim argumen/usulan ke meeting.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_submit_critique", "description": "Kirim kritik ke usulan di meeting.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_submit_rebuttal", "description": "Kirim rebuttal atas kritik.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_submit_revision", "description": "Kirim revisi usulan.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_record_decision", "description": "Catat keputusan meeting + dissent.",
     "permission": "write-sandbox", "scope": "meetings"},
    {"name": "meeting_get", "description": "Baca satu meeting beserta ronde-nya.",
     "permission": "read", "scope": "meetings"},
]

_VALID_PHASES = ("argument", "critique", "rebuttal", "revision")


def meeting_create(topic: str, participants: str = "") -> dict:
    """Buat meeting (rapat konsensus) baru. Mengembalikan meeting_id."""
    meeting_id = new_id("meet")
    record = {
        "meeting_id": meeting_id,
        "topic": topic,
        "participants": [p.strip() for p in participants.split(",") if p.strip()],
        "status": "created",
        "rounds": [],
        "decision": None,
        "created_at": utcnow(),
    }
    store.meetings[meeting_id] = record
    return ok(**record)


def _submit(meeting_id: str, phase: str, agent_id: str, content: str) -> dict:
    meeting = store.meetings.get(meeting_id)
    if meeting is None:
        return err("Meeting tidak ditemukan.", meeting_id=meeting_id)
    if phase not in _VALID_PHASES:
        return err(f"phase harus salah satu dari {list(_VALID_PHASES)}.", phase=phase)
    entry = {"phase": phase, "agent_id": agent_id, "content": content,
             "created_at": utcnow()}
    meeting.setdefault("rounds", []).append(entry)
    return ok(meeting_id=meeting_id, **entry)


def meeting_submit_argument(meeting_id: str, agent_id: str, content: str) -> dict:
    """Kirim argumen/usulan ke meeting."""
    return _submit(meeting_id, "argument", agent_id, content)


def meeting_submit_critique(meeting_id: str, agent_id: str, content: str) -> dict:
    """Kirim kritik ke usulan di meeting."""
    return _submit(meeting_id, "critique", agent_id, content)


def meeting_submit_rebuttal(meeting_id: str, agent_id: str, content: str) -> dict:
    """Kirim rebuttal atas kritik."""
    return _submit(meeting_id, "rebuttal", agent_id, content)


def meeting_submit_revision(meeting_id: str, agent_id: str, content: str) -> dict:
    """Kirim revisi usulan."""
    return _submit(meeting_id, "revision", agent_id, content)


def meeting_record_decision(meeting_id: str, decision: str,
                            dissent: str = "") -> dict:
    """Catat keputusan meeting (approve/revise/reject) + dissent."""
    meeting = store.meetings.get(meeting_id)
    if meeting is None:
        return err("Meeting tidak ditemukan.", meeting_id=meeting_id)
    if decision not in ("approve", "revise", "reject"):
        return err("decision harus approve, revise, atau reject.",
                   decision=decision)
    record = {"decision": decision,
              "dissent": [d.strip() for d in dissent.split(";") if d.strip()],
              "recorded_at": utcnow()}
    meeting["decision"] = record
    meeting["status"] = "decided"
    return ok(meeting_id=meeting_id, **record)


def meeting_get(meeting_id: str) -> dict:
    """Baca satu meeting beserta ronde-nya."""
    meeting = store.meetings.get(meeting_id)
    if meeting is None:
        return err("Meeting tidak ditemukan.", meeting_id=meeting_id)
    return ok(**meeting)


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain meeting ke ``mcp``."""
    for fn in (meeting_create, meeting_submit_argument, meeting_submit_critique,
               meeting_submit_rebuttal, meeting_submit_revision,
               meeting_record_decision, meeting_get):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
