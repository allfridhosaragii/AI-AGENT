"""Test Manual Handoff MUFAKAT Room (V3 Addendum F) — mode default.

- State machine DRAFT -> ... -> APPROVED; transisi ilegal ditolak.
- State tidak maju seolah provider menjawab bila belum ada impor.
- Prompt diblokir secret scanner; pacing dijaga saat copy.
- Respons impor berlabel "user imported" + provenance lengkap.
- Konsensus Borda reuse mufakat.consensus.voting.
- Persistensi JSON + SQLite RoomStore.
"""


import pytest

from mufakat.room.handoff import Room, RoomError
from mufakat.room.pacing import PacingLedger
from mufakat.room.storage import RoomStore

MOCK_REPLY = (
    "Usulan: FastAPI.\n"
    "```json\n"
    '{"phase": "proposal", "summary": "FastAPI + SQLite.", "proposal": "FastAPI",'
    ' "vote": {"decision": "approve", "ranking": ["A", "B", "C"], "confidence": 0.8}}\n'
    "```"
)


def _room(tmp_path, providers=("chatgpt", "claude", "gemini")):
    return Room(
        room_id="room-test-1",
        idea="Buat REST API todo",
        providers=list(providers),
        room_dir=tmp_path / "room",
        pacing_ledger=PacingLedger(),
    )


def test_handoff_alur_penuh_manual(tmp_path):
    room = _room(tmp_path)
    assert room.state == "DRAFT"
    prompts = room.build_prompts(template="proposal")
    assert set(prompts) == {"chatgpt", "claude", "gemini"}
    assert room.state == "READY_TO_SEND"
    text = room.copy_prompt("chatgpt")
    assert "Buat REST API todo" in text
    assert room.state == "WAITING_FOR_USER_SUBMISSION"
    room.mark_submitted("chatgpt")
    assert room.state == "WAITING_FOR_IMPORTED_RESPONSE"
    record = room.import_response("chatgpt", MOCK_REPLY)
    assert record["source"] == "user imported"
    assert record["provider"] == "chatgpt"
    assert record["round"] == 1
    assert record["parse_status"] == "ok"
    assert record["imported_at"]
    assert room.state == "RESPONSE_IMPORTED"
    assert room.transition("finalize") == "FINAL_REVIEW"
    assert room.transition("approve") == "APPROVED"


def test_handoff_tidak_maju_tanpa_impor(tmp_path):
    room = _room(tmp_path)
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    with pytest.raises(RoomError):
        room.transition("response_imported")


def test_handoff_transisi_ilegal_ditolak(tmp_path):
    room = _room(tmp_path)
    with pytest.raises(RoomError):
        room.transition("approve")
    with pytest.raises(RoomError):
        room.copy_prompt("chatgpt")  # belum ada prompt ronde ini


def test_handoff_secret_dalam_ide_memblokir_prompt(tmp_path):
    room = Room(
        room_id="room-secret",
        idea='Pakai api_key = "sk-abcdefghijklmnopqrstuv" ini',
        providers=["chatgpt"],
        room_dir=tmp_path / "room",
        pacing_ledger=PacingLedger(),
    )
    with pytest.raises(RoomError):
        room.build_prompts()


def test_handoff_pacing_memblokir_copy_cepat(tmp_path):
    clock = [1_000_000.0]
    ledger = PacingLedger(clock=lambda: clock[0])
    room = Room(
        room_id="room-pacing",
        idea="Ide",
        providers=["chatgpt"],
        room_dir=tmp_path / "room",
        pacing_ledger=ledger,
    )
    room.build_prompts()
    assert room.copy_prompt("chatgpt")
    # Copy kedua ke provider yang sama sebelum 20 detik -> ditolak.
    # (Bangun ulang prompt ronde yang sama untuk menguji pacing copy.)
    room.prompts["chatgpt"] = {"template": "proposal", "text": "prompt ulang"}
    with pytest.raises(RoomError):
        room.copy_prompt("chatgpt")


def test_handoff_impor_tanpa_json_tetap_disimpan_unparsed(tmp_path):
    room = _room(tmp_path)
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    record = room.import_response("chatgpt", "Jawaban tanpa blok json sama sekali.")
    assert record["parse_status"] == "unparsed"
    assert record["raw_text"].startswith("Jawaban tanpa")
    assert room.state == "RESPONSE_IMPORTED"


def test_handoff_konsensus_borda(tmp_path):
    room = _room(tmp_path)
    room.build_prompts()
    for provider in ("chatgpt", "claude", "gemini"):
        room.copy_prompt(provider)
    room.mark_submitted("chatgpt")
    for provider in ("chatgpt", "claude", "gemini"):
        room.import_response(provider, MOCK_REPLY)
    consensus = room.consensus()
    assert consensus is not None
    assert consensus["decision"] == "mufakat"
    assert consensus["winner"] == "A"


def test_handoff_konsensus_tanpa_vote_none(tmp_path):
    room = _room(tmp_path)
    assert room.consensus() is None


def test_handoff_batas_ronde(tmp_path):
    room = _room(tmp_path)
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    assert room.next_round() == 2
    assert room.round_no == 2
    assert room.state == "READY_TO_SEND"
    assert room.prompts == {}


def test_handoff_persistensi_dan_load(tmp_path):
    room = _room(tmp_path)
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    loaded = Room.load(tmp_path / "room")
    assert loaded.room_id == room.room_id
    assert loaded.state == "RESPONSE_IMPORTED"
    assert len(loaded.responses) == 1
    assert loaded.responses[0]["source"] == "user imported"
    assert (tmp_path / "room" / "transcript.jsonl").is_file()


def test_handoff_provider_tidak_dikenal_ditolak(tmp_path):
    with pytest.raises(ValueError):
        Room(room_id="x", idea="ide", providers=["tidak_ada"], room_dir=tmp_path)


def test_room_store_sqlite(tmp_path):
    store = RoomStore(tmp_path / "room.db")
    room = _room(tmp_path)
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    record = room.import_response("chatgpt", MOCK_REPLY)
    store.save_room(room)
    store.save_response(room.room_id, record)
    store.record_usage(room.room_id, "chatgpt", "2026-11-20")
    store.record_usage(room.room_id, "chatgpt", "2026-11-20")
    assert store.usage_today(room.room_id, "chatgpt", "2026-11-20") == 2
    responses = store.list_responses(room.room_id)
    assert len(responses) == 1
    assert responses[0]["source"] == "user imported"
    markdown = store.export_markdown(room.room_id)
    assert "user imported" in markdown
    assert "FastAPI" in markdown
    store.close()


def test_room_store_room_tidak_ditemukan(tmp_path):
    store = RoomStore(tmp_path / "room.db")
    with pytest.raises(ValueError):
        store.export_markdown("tidak_ada")
    store.close()
