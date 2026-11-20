"""Test engine MUFAKAT Room: secret scan, pacing, parser, provider, anti-loop, state machine."""

import pytest

from mufakat.room.anti_loop import AntiLoop, hash_diff_findings
from mufakat.room.pacing import PacingLedger
from mufakat.room.parser import extract_last_json_block, format_repair_prompt, parse_reply
from mufakat.room.prompts import render_prompt
from mufakat.room.providers import (
    get_provider,
    honest_status_label,
    list_providers,
)
from mufakat.room.secret_scan import contains_secret, redact_matches, scan_text
from mufakat.room.state_machine import DebateMachine, IllegalTransition


def test_secret_scan_memblokir_api_key():
    assert contains_secret('api_key = "sk-abcdefghijklmnopqrstuv"')
    assert contains_secret("-----BEGIN PRIVATE KEY-----")
    assert contains_secret("AKIAIOSFODNN7EXAMPLE")
    assert contains_secret('password = "rahasia123"')
    assert contains_secret("lihat file .env saya")
    assert not contains_secret("Buat REST API todo dengan FastAPI.")


def test_secret_scan_redact_tidak_membocorkan_nilai():
    redacted = redact_matches('api_key = "sk-abcdefghijklmnopqrstuv"')
    assert "sk-abcdefghijklmnopqrstuv" not in redacted
    assert "[REDACTED:" in redacted
    findings = scan_text('api_key = "sk-abcdefghijklmnopqrstuv"')
    assert findings and findings[0].pattern in ("credential_assignment", "openai_key")
    assert "sk-abcdefghijklmnopqrstuv" not in findings[0].preview


def test_pacing_jeda_20_detik():
    clock = [1_000_000.0]
    ledger = PacingLedger(clock=lambda: clock[0])
    assert ledger.check("chatgpt").allowed is True
    assert ledger.record("chatgpt").allowed is True
    decision = ledger.check("chatgpt")
    assert decision.allowed is False
    assert decision.wait_seconds > 0
    clock[0] += 21
    assert ledger.check("chatgpt").allowed is True


def test_pacing_batas_harian_40():
    clock = [1_000_000.0]
    ledger = PacingLedger(daily_limit=2, clock=lambda: clock[0])
    for _ in range(2):
        assert ledger.record("chatgpt").allowed is True
        clock[0] += 21
    decision = ledger.check("chatgpt")
    assert decision.allowed is False
    assert "Batas harian" in decision.reason


def test_pacing_beda_situs_tidak_saling_mengunci():
    ledger = PacingLedger()
    assert ledger.record("chatgpt").allowed is True
    assert ledger.check("claude").allowed is True


def test_parser_blok_terakhir_ok():
    text = (
        'dulu ```json\n{"phase": "proposal", "summary": "a"}\n``` lalu '
        '```json\n{"phase": "proposal", "summary": "b"}\n```'
    )
    assert '"b"' in (extract_last_json_block(text) or "")
    result = parse_reply(text)
    assert result.status == "ok"
    assert result.payload["summary"] == "b"


def test_parser_tanpa_json_unparsed():
    assert parse_reply("hanya teks biasa").status == "unparsed"


def test_parser_rusak_repair_sekali():
    broken = '```json\n{"phase": "proposal",\n```'
    assert parse_reply(broken).status == "repair_needed"
    assert parse_reply(broken, repair_attempted=True).status == "unparsed"
    assert "format" in format_repair_prompt("JSON rusak").lower()


def test_provider_default_manual_handoff():
    for provider in list_providers():
        assert provider.manual_handoff_supported is True
        assert provider.automated_prompt_submission_allowed is False
        assert provider.automated_response_retrieval_allowed is False
        assert provider.official_connection_supported is False
    assert get_provider("chatgpt").integration_status == "manual_handoff"
    assert get_provider("muse").integration_status == "needs_policy_review"


def test_provider_label_jujur_bukan_connected():
    assert honest_status_label(get_provider("chatgpt")) == "Manual handoff only"
    assert honest_status_label(get_provider("muse")) == "Needs policy review"
    for provider in list_providers():
        assert honest_status_label(provider) != "Connected"
    with pytest.raises(ValueError):
        get_provider("tidak_ada")


def test_prompts_semua_template_dirender():
    for template in ("proposal", "critique", "meeting", "rebuttal", "spec", "code",
                     "review", "audit", "test", "revise"):
        rendered = render_prompt(template, idea="ide X", context="ctx", role="debater",
                                 disputes="d1", findings="f1")
        assert "```json" in rendered
        # Hanya template proposal yang memakai {idea}; lainnya memakai
        # {context}/{disputes}/{findings} sesuai perannya.
        if template == "proposal":
            assert "ide X" in rendered
        else:
            assert "ctx" in rendered or "d1" in rendered or "f1" in rendered
    with pytest.raises(ValueError):
        render_prompt("tidak_ada")


def test_anti_loop_hash_berulang_eskalasi():
    loop = AntiLoop()
    first = loop.observe("diff-a", [{"rule": "x"}])
    assert first["escalate"] is False
    second = loop.observe("diff-a", [{"rule": "x"}])
    assert second["escalate"] is True
    assert second["repeated_hash"] is True
    assert hash_diff_findings("d", [{"a": 1}]) == hash_diff_findings("d", [{"a": 1}])


def test_anti_loop_temuan_stagnan_eskalasi():
    loop = AntiLoop()
    loop.observe("d1", [{"r": 1}, {"r": 2}])
    loop.observe("d2", [{"r": 1}, {"r": 2}])
    third = loop.observe("d3", [{"r": 1}, {"r": 2}])
    assert third["escalate"] is True
    assert third["stagnant_findings"] is True


def test_state_machine_debat_sampai_spesifikasi():
    machine = DebateMachine()
    assert machine.transition("kirim_ide") == "usulan_r1"
    assert machine.transition("usulan_diterima") == "kritik_silang"
    assert machine.transition("kritik_diterima") == "rapat"
    assert machine.transition("mufakat_atau_juri") == "spesifikasi"
    assert machine.is_terminal is False


def test_state_machine_transisi_ilegal_ditolak():
    machine = DebateMachine()
    with pytest.raises(IllegalTransition):
        machine.transition("kode_selesai")


def test_state_machine_eskalasi_batas_ronde():
    machine = DebateMachine()
    machine.transition("kirim_ide")
    machine.transition("usulan_diterima")
    machine.transition("kritik_diterima")
    machine.transition("belum_mufakat")
    assert machine.transition("debat_lanjut") == "kritik_silang"
    machine.transition("kritik_diterima")
    machine.transition("belum_mufakat")
    assert machine.transition("debat_lanjut") == "eskalasi"
    assert machine.is_terminal is True
