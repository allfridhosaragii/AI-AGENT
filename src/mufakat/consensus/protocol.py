"""Protokol pesan konsensus MUFAKAT (JSON Schema Claude §8).

Modul ini hanya bergantung pada Pydantic v2 dan pustaka standar, agar
skema pesan bisa dipakai tanpa mengimpor modul MUFAKAT lainnya.

Setiap pesan antar-agent adalah satu :class:`MufakatMessage` yang
diserialisasi sebagai satu baris JSONL di transkrip run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "Phase",
    "Role",
    "ModelFamily",
    "Stance",
    "MufakatMessage",
    "model_json_schema",
    "to_jsonl",
    "from_jsonl",
]


class Phase(str, Enum):
    """Fase alur konsensus."""

    RESEARCH = "research"
    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    MEETING = "meeting"
    REBUTTAL = "rebuttal"
    SPEC = "spec"
    CODE = "code"
    REVIEW = "review"
    AUDIT = "audit"
    TEST = "test"
    REVISE = "revise"
    VERDICT = "verdict"


class Role(str, Enum):
    """Peran agent dalam satu run."""

    RESEARCHER = "researcher"
    PLANNER = "planner"
    ARCHITECT = "architect"
    DEBATER = "debater"
    MODERATOR = "moderator"
    CODER = "coder"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"
    TESTER = "tester"


class ModelFamily(str, Enum):
    """Keluarga model / provider yang dipakai agent."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    META = "meta"
    OTHER = "other"


class Stance(str, Enum):
    """Posisi debater terhadap proposal."""

    PRO = "pro"
    CONTRA = "contra"
    NEUTRAL = "neutral"


class MufakatMessage(BaseModel):
    """Satu pesan antar-agent dalam protokol MUFAKAT.

    ``content`` adalah dict bebas dengan kunci yang umum dipakai:
    ``summary`` (maks. 1200 karakter), ``proposal``, ``claims``,
    ``critiques``, ``vote``, dan ``usage``.
    """

    run_id: str = Field(..., min_length=1, description="ID run konsensus.")
    round: int = Field(..., ge=1, description="Nomor ronde, mulai dari 1.")
    phase: Phase = Field(..., description="Fase alur saat pesan dibuat.")
    agent_id: str = Field(..., min_length=1, description="ID unik agent pengirim.")
    role: Role = Field(..., description="Peran agent pengirim.")
    model_family: ModelFamily = Field(..., description="Keluarga model agent.")
    stance: Optional[Stance] = Field(
        default=None, description="Posisi debater; kosong untuk peran non-debater."
    )
    content: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Isi pesan: summary (maks. 1200 karakter), proposal, claims, "
            "critiques, vote, usage."
        ),
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Waktu pembuatan pesan (UTC).",
    )

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Batasi panjang ringkasan agar transkrip tetap ringkas."""
        summary = value.get("summary")
        if summary is not None and len(str(summary)) > 1200:
            raise ValueError("content.summary tidak boleh lebih dari 1200 karakter.")
        return value


def model_json_schema() -> dict[str, Any]:
    """Kembalikan JSON Schema (Pydantic v2) untuk :class:`MufakatMessage`."""
    return MufakatMessage.model_json_schema()


def to_jsonl(message: MufakatMessage) -> str:
    """Serialisasi satu pesan menjadi satu baris JSONL."""
    return message.model_dump_json()


def from_jsonl(line: str) -> MufakatMessage:
    """Parse satu baris JSONL menjadi :class:`MufakatMessage`."""
    data = json.loads(line)
    return MufakatMessage.model_validate(data)
