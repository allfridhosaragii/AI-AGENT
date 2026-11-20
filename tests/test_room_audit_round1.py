"""Test regresi audit ekstrem Putaran 1 (20 Nov 2026).

Setiap test di sini mengunci satu bug yang ditemukan pada audit
Putaran 1 — bila test ini gagal, bug itu kembali.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mufakat-room" / "runner"))

from mufakat.consensus.voting import borda_count, decide, detect_false_consensus
from mufakat.gates.runner import GateResult
from mufakat.gates.verdict import verdict
from mufakat.room.anti_loop import AntiLoop, hash_diff_findings
from mufakat.room.handoff import Room, RoomError
from mufakat.room.pacing import PacingLedger
from mufakat.room.parser import extract_last_json_block, parse_reply
from mufakat.room.secret_scan import contains_secret, scan_text
from mufakat.room.state_machine import DebateMachine, IllegalTransition
from mufakat.room.storage import RoomStore
from mufakat.sandbox.worktree import create_worktree, remove_worktree, validate_run_id

MOCK_REPLY = (
    "Usulan: FastAPI.\n"
    "```json\n"
    '{"phase": "proposal", "summary": "FastAPI + SQLite.", "proposal": "FastAPI",'
    ' "vote": {"decision": "approve", "ranking": ["A", "B", "C"], "confidence": 0.8}}\n'
    "```"
)
BROKEN_REPLY = '```json\n{"phase": "proposal",\n```'


def _room(tmp_path, providers=("chatgpt", "claude", "gemini")):
    return Room(
        room_id="room-audit-1",
        idea="Buat REST API todo",
        providers=list(providers),
        room_dir=tmp_path / "room",
        pacing_ledger=PacingLedger(),
    )


# -- Borda / konsensus ---------------------------------------------------
def test_borda_duplikat_dalam_ranking_dihitung_sekali():
    assert borda_count([["A", "A", "B"]]) == {"A": 1, "B": 0}


def test_borda_ranking_string_tidak_dihitung_per_huruf():
    result = decide([{"decision": "approve", "ranking": "ABC"}], [])
    assert result["borda"] == {}
    assert result["winner"] is None


def test_borda_ranking_tak_hashable_tidak_crash():
    assert borda_count([[["x"], "A"]]) == {"A": 0}


def test_decide_vote_decision_tidak_valid_diabaikan():
    result = decide(
        [{"decision": "maybe", "ranking": ["A"]},
         {"decision": "approve", "ranking": ["A"]}],
        [],
    )
    assert result["approve_ratio"] == 1.0
    assert result["decision"] == "mufakat"


def test_decide_voter_sama_hanya_dihitung_sekali():
    result = decide(
        [{"agent_id": "x", "decision": "approve", "ranking": ["A", "B"]},
         {"agent_id": "x", "decision": "approve", "ranking": ["A", "B"]},
         {"agent_id": "y", "decision": "approve", "ranking": ["B", "A"]}],
        [],
    )
    assert result["borda"] == {"A": 1, "B": 1}
    assert result["decision"] == "tie"


def test_decide_tie_tidak_menutupi_blocking():
    result = decide(
        [{"decision": "approve", "ranking": ["A", "B"]},
         {"decision": "approve", "ranking": ["B", "A"]}],
        [{"severity": "blocking"}],
    )
    assert result["decision"] == "belum_mufakat"
    assert result["blocking"] == 1
    assert result["winner"] is None


def test_false_consensus_teks_kosong_bukan_sepakat_palsu():
    assert detect_false_consensus(["", ""]) is False
    assert detect_false_consensus(["   ", "   "]) is False


# -- Parser --------------------------------------------------------------
def test_parser_blok_json_satu_baris():
    result = parse_reply('```json {"phase": "proposal", "summary": "a"}```')
    assert result.status == "ok"
    assert result.payload["summary"] == "a"


def test_parser_spasi_sebelum_label_json():
    result = parse_reply('``` json\n{"phase": "proposal", "summary": "a"}\n```')
    assert result.status == "ok"


def test_parser_fence_polos_setelah_json_diabaikan():
    text = (
        '```json\n{"phase": "proposal", "summary": "a"}\n```\n'
        "```\ncode biasa\n```"
    )
    assert parse_reply(text).status == "ok"
    assert extract_last_json_block(text) is not None
    assert '"a"' in extract_last_json_block(text)


def test_parser_fence_python_setelah_json_diabaikan():
    text = (
        '```json\n{"phase": "proposal", "summary": "a"}\n```\n'
        "```python\nprint(1)\n```"
    )
    assert parse_reply(text).status == "ok"


def test_parser_vote_tidak_valid_minta_repair():
    text = (
        '```json\n{"phase": "proposal", "summary": "a", '
        '"vote": {"decision": "maybe", "ranking": ["A"]}}\n```'
    )
    assert parse_reply(text).status == "repair_needed"


def test_parser_ranking_bukan_list_minta_repair():
    text = (
        '```json\n{"phase": "proposal", "summary": "a", '
        '"vote": {"decision": "approve", "ranking": "ABC"}}\n```'
    )
    assert parse_reply(text).status == "repair_needed"


# -- Secret scan ---------------------------------------------------------
@pytest.mark.parametrize("secret", [
    "sk-proj-abcdefghijklmnopqrstuvwx",
    "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnopqrstuvwx",
    "AIzaSyA1234567890abcdefghijklmnopqrstuvwx",
    "xoxb-1234567890-abcdefghij",
    "-----begin private key-----",
    'api key = "secret123"',
])
def test_secret_scan_pola_baru_terdeteksi(secret):
    assert contains_secret(secret), secret


def test_secret_scan_satu_secret_satu_temuan():
    findings = scan_text('api_key = "sk-abcdefghijklmnopqrstuv"')
    assert len(findings) == 1
    assert "sk-abcdefghijklmnopqrstuv" not in findings[0].preview


# -- Pacing --------------------------------------------------------------
def test_pacing_hari_utc_berganti_dengan_clock_inject():
    clock = [1_700_000_000.0]  # 2023-11-14 UTC
    ledger = PacingLedger(daily_limit=1, clock=lambda: clock[0])
    assert ledger.record("chatgpt").allowed is True
    assert ledger.check("chatgpt").allowed is False
    clock[0] += 90_000  # +25 jam -> hari UTC berikutnya
    assert ledger.check("chatgpt").allowed is True
    assert ledger.used_today("chatgpt") == 0


def test_pacing_batas_negatif_ditolak():
    with pytest.raises(ValueError):
        PacingLedger(daily_limit=-1)
    with pytest.raises(ValueError):
        PacingLedger(min_interval_seconds=-5)


def test_pacing_hitungan_lama_diprune():
    ledger = PacingLedger()
    ledger._daily = {"chatgpt": {"2020-01-01": 40, "2020-01-02": 3}}
    ledger._prune_old_days(ledger._today())
    assert "2020-01-01" not in ledger._daily.get("chatgpt", {})


# -- Anti-loop -----------------------------------------------------------
def test_anti_loop_hash_temuan_tak_json_tidak_crash():
    digest = hash_diff_findings("d", [{"x": {1, 2}}])
    assert digest == hash_diff_findings("d", [{"x": {1, 2}}])


def test_anti_loop_hash_abaikan_spasi_akhir_diff():
    assert hash_diff_findings("d\n", [{"a": 1}]) == hash_diff_findings("d", [{"a": 1}])
    loop = AntiLoop()
    loop.observe("diff-a\n", [{"r": 1}])
    assert loop.observe("diff-a", [{"r": 1}])["escalate"] is True


def test_anti_loop_reset():
    loop = AntiLoop()
    loop.observe("d", [{"r": 1}])
    loop.reset()
    assert loop.observe("d", [{"r": 1}])["escalate"] is False


# -- State machine -------------------------------------------------------
def test_state_machine_total_iterations_menghitung_semua_transisi():
    machine = DebateMachine()
    machine.transition("kirim_ide")
    machine.transition("usulan_diterima")
    assert machine.total_iterations == 2


def test_state_machine_state_awal_tidak_valid_ditolak():
    with pytest.raises((IllegalTransition, ValueError)):
        DebateMachine(state="bogus")


# -- Handoff -------------------------------------------------------------
def test_handoff_providers_kosong_ditolak():
    with pytest.raises(RoomError):
        Room(room_id="x", idea="ide", providers=[])


def test_handoff_alur_repair_format_bisa_jalan(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    # Repair sebelum ada jawaban rusak -> ditolak (bukan prompt menyesatkan).
    with pytest.raises(RoomError):
        room.format_repair_prompt("chatgpt")
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    record = room.import_response("chatgpt", BROKEN_REPLY)
    assert record["parse_status"] == "repair_needed"
    prompt = room.format_repair_prompt("chatgpt")
    assert "```json" in prompt
    # Prompt repair hanya 1x.
    with pytest.raises(RoomError):
        room.format_repair_prompt("chatgpt")
    # Impor rusak kedua (percobaan repair) -> unparsed, bukan repair_needed lagi.
    record2 = room.import_response("chatgpt", BROKEN_REPLY)
    assert record2["parse_status"] == "unparsed"
    # Impor bagus sesudahnya mengganti record (bukan menumpuk).
    record3 = room.import_response("chatgpt", MOCK_REPLY)
    assert record3["parse_status"] == "ok"
    assert len(room.responses) == 1


def test_handoff_impor_ganda_tidak_menggandakan_suara(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    room.import_response("chatgpt", MOCK_REPLY)
    assert len(room.responses) == 1
    assert room.consensus()["borda"] == {"A": 2, "B": 1, "C": 0}


def test_handoff_fase_salah_tidak_menyimpan_dan_tidak_desync(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    room.transition("critique_prepared")
    room.transition("critique_sent")
    before_disk = (tmp_path / "room" / "room.json").read_text(encoding="utf-8")
    with pytest.raises(RoomError):
        room.import_response("chatgpt", MOCK_REPLY)  # phase proposal, harus rebuttal
    assert len(room.responses) == 1
    assert room.state == "WAITING_FOR_REBUTTAL_IMPORT"
    assert (tmp_path / "room" / "room.json").read_text(encoding="utf-8") == before_disk
    record = room.import_response("chatgpt", MOCK_REPLY, phase="rebuttal")
    assert record["phase"] == "rebuttal"
    assert room.state == "REVISION_READY"


def test_handoff_provider_bukan_anggota_ditolak(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    with pytest.raises(RoomError):
        room.import_response("claude", MOCK_REPLY)
    with pytest.raises(RoomError):
        room.mark_submitted("claude")


def test_handoff_next_round_langsung_ditolak_dan_next_round_benar(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    with pytest.raises(RoomError):
        room.transition("next_round")
    assert room.next_round() == 2
    assert room.round_no == 2
    assert room.prompts == {}
    assert room.state == "READY_TO_SEND"


def test_handoff_mark_submitted_state_salah_ditolak(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    with pytest.raises(RoomError):
        room.mark_submitted("chatgpt")  # masih DRAFT


def test_handoff_build_prompts_atomik_saat_diblokir(tmp_path):
    room = Room(
        room_id="room-secret",
        idea='Pakai api_key = "sk-abcdefghijklmnopqrstuv" ini',
        providers=["chatgpt"],
        room_dir=tmp_path / "room",
        pacing_ledger=PacingLedger(),
    )
    with pytest.raises(RoomError):
        room.build_prompts()
    assert room.prompts == {}
    assert room.state == "DRAFT"


def test_handoff_konsensus_abaikan_vote_rebuttal_dan_tidak_valid(tmp_path):
    room = _room(tmp_path, providers=("chatgpt", "claude"))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    # Vote rebuttal (fase berbeda) tidak boleh ikut dihitung.
    bad_vote = MOCK_REPLY.replace('"decision": "approve"', '"decision": "reject"')
    room.import_response("chatgpt", bad_vote, phase="rebuttal")
    consensus = room.consensus()
    assert consensus is not None
    assert consensus["decision"] == "mufakat"
    assert consensus["approve_ratio"] == 1.0


def test_handoff_load_memulihkan_pacing_dan_repair(tmp_path):
    ledger = PacingLedger(path=tmp_path / "usage.json")
    room = Room(
        room_id="room-load",
        idea="ide",
        providers=["chatgpt"],
        room_dir=tmp_path / "room",
        pacing_ledger=ledger,
    )
    room.build_prompts()
    room.copy_prompt("chatgpt")
    loaded = Room.load(tmp_path / "room")
    # Ledger dipulihkan: copy lagi <20 detik tetap diblokir pacing.
    assert loaded.pacing.check("chatgpt").allowed is False
    assert loaded.state == "WAITING_FOR_USER_SUBMISSION"


def test_handoff_load_file_rusak_menghasilkan_room_error(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "room.json").write_text('{"room_id": 1}', encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)
    (bad / "room.json").write_text('[1, 2]', encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)
    (bad / "room.json").write_text('bukan json', encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)
    (bad / "room.json").write_text('{"room_id": "x", "idea": "i", "providers": ["chatgpt"], '
                                   '"state": "BOGUS", "round_no": 1}', encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)


# -- Storage / verdict / worktree ---------------------------------------
def test_storage_export_markdown_meredaksi_secret(tmp_path):
    store = RoomStore(tmp_path / "room.db")
    room = _room(tmp_path, providers=("chatgpt",))
    record = {
        "provider": "chatgpt", "round": 1, "phase": "proposal",
        "source": "user imported", "imported_at": "2026-11-20T00:00:00Z",
        "raw_text": 'jawaban api_key = "sk-abcdefghijklmnopqrstuv"',
        "parse_status": "ok", "parsed": None,
    }
    store.save_room(room)
    store.save_response(room.room_id, record)
    markdown = store.export_markdown(room.room_id)
    assert "sk-abcdefghijklmnopqrstuv" not in markdown
    assert "[REDACTED:" in markdown
    store.close()


def test_storage_save_response_kunci_hilang_ditolak(tmp_path):
    store = RoomStore(tmp_path / "room.db")
    with pytest.raises(ValueError):
        store.save_response("r1", {"provider": "chatgpt"})
    store.close()


def test_verdict_temuan_string_tidak_crash():
    result = verdict([GateResult(tool="bandit", passed=False, findings=["oops"])])
    assert result["safe"] is False
    assert result["status"] == "TIDAK AMAN"


def test_worktree_run_id_traversal_ditolak(tmp_path):
    with pytest.raises(ValueError):
        validate_run_id("../../evil")
    with pytest.raises(ValueError):
        validate_run_id("a/b")
    with pytest.raises(ValueError):
        create_worktree(tmp_path, "../../evil")


def test_worktree_remove_berbahaya_ditolak(tmp_path):
    assert remove_worktree("/") is False
    assert remove_worktree(str(Path.home())) is False
    # Folder biasa tetap bisa dihapus.
    target = tmp_path / "wt"
    target.mkdir()
    assert remove_worktree(target) is True
    assert not target.exists()


# -- Regresi audit Putaran 2 (audit ulang atas perbaikan Putaran 1) ----
def test_round2_remove_worktree_sah_di_dalam_repo_boleh(tmp_path):
    repo = tmp_path / "repo"
    wt = repo / "runs" / "r1" / "wt"
    wt.mkdir(parents=True)
    (wt / "f.txt").write_text("x")
    assert remove_worktree(wt, repo) is True
    assert not wt.exists()


def test_round2_remove_worktree_leluhur_repo_ditolak(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert remove_worktree(tmp_path, repo) is False
    assert tmp_path.exists()
    assert remove_worktree(repo, repo) is False
    assert repo.exists()


def test_round2_mark_submitted_idempotent(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.mark_submitted("chatgpt")  # panggilan kedua tidak boleh error
    assert room.state == "WAITING_FOR_IMPORTED_RESPONSE"


def test_round2_impor_setelah_approved_ditolak(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", MOCK_REPLY)
    room.transition("finalize")
    room.transition("approve")
    with pytest.raises(RoomError):
        room.import_response("chatgpt", MOCK_REPLY)
    assert len(room.responses) == 1


def test_round2_repair_setelah_impor_bagus_ditolak(tmp_path):
    room = _room(tmp_path, providers=("chatgpt",))
    room.build_prompts()
    room.copy_prompt("chatgpt")
    room.mark_submitted("chatgpt")
    room.import_response("chatgpt", BROKEN_REPLY)
    room.import_response("chatgpt", MOCK_REPLY)  # jawaban bagus mengganti yang rusak
    with pytest.raises(RoomError):
        room.format_repair_prompt("chatgpt")


def test_round2_load_prompts_atau_responses_malformed_ditolak(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    base = {"room_id": "x", "idea": "i", "providers": ["chatgpt"],
            "state": "DRAFT", "round_no": 1}
    (bad / "room.json").write_text(json.dumps(
        {**base, "prompts": {"chatgpt": "bukan-dict"}, "responses": []}),
        encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)
    (bad / "room.json").write_text(json.dumps(
        {**base, "prompts": {}, "responses": ["bukan-dict"]}),
        encoding="utf-8")
    with pytest.raises(RoomError):
        Room.load(bad)


def test_round2_anti_loop_findings_none_tidak_crash():
    assert hash_diff_findings("d", None) == hash_diff_findings("d", [])
    assert AntiLoop().observe("d", None)["escalate"] is False
