"""MUFAKAT Room — engine Python (manual handoff sebagai default).

Mode default: MANUAL HANDOFF (V3 §2.2 Mode B). Assisted Fill via
extension HANYA modul opt-in Fase 2, terpisah, tidak aktif secara
default (lihat ``mufakat-room/`` — scaffold, belum terverifikasi).
Tidak ada auto-send, tidak ada pembacaan cookie/token, tidak ada
otomasi situs AI.
"""

from mufakat.room.anti_loop import AntiLoop, hash_diff_findings
from mufakat.room.handoff import HANDOFF_STATES, MAX_HANDOFF_ROUNDS, Room, RoomError
from mufakat.room.pacing import DEFAULT_DAILY_LIMIT, DEFAULT_MIN_INTERVAL_SECONDS, PacingLedger
from mufakat.room.parser import ParseResult, extract_last_json_block, parse_reply
from mufakat.room.prompts import PROMPT_TEMPLATES, render_prompt
from mufakat.room.providers import PROVIDERS, get_provider, honest_status_label, list_providers
from mufakat.room.secret_scan import SecretFinding, contains_secret, scan_text
from mufakat.room.state_machine import MAX_DEBATE_ROUNDS, DebateMachine
from mufakat.room.storage import RoomStore

__all__ = [
    "AntiLoop",
    "DebateMachine",
    "HANDOFF_STATES",
    "MAX_DEBATE_ROUNDS",
    "MAX_HANDOFF_ROUNDS",
    "PROMPT_TEMPLATES",
    "PROVIDERS",
    "ParseResult",
    "PacingLedger",
    "Room",
    "RoomError",
    "RoomStore",
    "SecretFinding",
    "DEFAULT_DAILY_LIMIT",
    "DEFAULT_MIN_INTERVAL_SECONDS",
    "contains_secret",
    "extract_last_json_block",
    "get_provider",
    "hash_diff_findings",
    "honest_status_label",
    "list_providers",
    "parse_reply",
    "render_prompt",
    "scan_text",
]
