"""Test A2A minimal MUFAKAT — Agent Card + Task/artifact envelope.

Yang diuji: format card, round-trip JSON, pembuatan task, dan
dispatch lokal (handler terdaftar -> completed; tanpa handler ->
failed dengan pesan jujur). Interop dengan agent A2A eksternal
TIDAK diuji di sini — belum terverifikasi.
"""

from __future__ import annotations

import pytest

from mufakat.a2a import (
    AgentCard,
    AgentSkill,
    Artifact,
    Message,
    Part,
    TaskState,
    create_agent_card,
    create_task,
    dispatch_task,
    register_handler,
)


def test_agent_card_round_trip_json():
    card = create_agent_card(
        "mufakat-coder", "http://localhost:8000",
        description="Coder MUFAKAT",
        skills=[AgentSkill(id="code", name="Coding",
                           description="Menulis kode Python")])
    assert card.name == "mufakat-coder"
    assert card.capabilities.state_transition_history is True
    restored = AgentCard.from_json(card.to_json())
    assert restored == card


def test_agent_card_wajib_nama_dan_url():
    with pytest.raises(Exception):
        AgentCard(name="", url="")
    with pytest.raises(Exception):
        AgentCard(name="x", url="")


def test_task_dispatch_handler_lokal():
    def handler(task):
        task.add_artifact(Artifact(name="hasil", parts=[Part(text="selesai")]))
        return task

    register_handler("coder-lokal", handler)
    task = create_task("ctx-1", Message(role="user", parts=[Part(text="buat todo")]))
    result = dispatch_task(task, "coder-lokal")
    assert result.status.state == TaskState.COMPLETED
    assert len(result.artifacts) == 1
    assert result.artifacts[0].parts[0].text == "selesai"


def test_task_dispatch_tanpa_handler_gagal_jujur():
    task = create_task("ctx-2", Message(role="user", parts=[Part(text="halo")]))
    result = dispatch_task(task, "agent-yang-tidak-ada")
    assert result.status.state == TaskState.FAILED
    assert result.status.message is not None
    assert "belum terverifikasi" in result.status.message.text()


def test_message_text_gabungan_parts():
    msg = Message(role="user", parts=[Part(text="satu"), Part(text="dua")])
    assert msg.text() == "satu\ndua"
    assert msg.role == "user"
