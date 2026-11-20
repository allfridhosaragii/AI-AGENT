"""Lapisan penyimpanan MUFAKAT: SQLModel di atas SQLite.

Berisi tabel inti run konsensus (``Run``, ``Message``, ``GateResult``,
``UsageLedger``) plus entitas kolaborasi ala ChatGPT (``Project``,
``Task``, ``Meeting``, ``MeetingRound``, ``Decision``,
``DecisionDissent``, ``Approval``, ``AuditLog``, ``Artifact``,
``ProviderConnection``, ``AgentDefinition``).

Jalur database tidak di-hardcode: pemanggil memberi ``path`` ke
:func:`init_db` / :func:`get_session` (mis. dari ``MUFAKAT_DB``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

__all__ = [
    "Run",
    "Message",
    "GateResult",
    "UsageLedger",
    "Project",
    "Task",
    "Meeting",
    "MeetingRound",
    "Decision",
    "DecisionDissent",
    "Approval",
    "AuditLog",
    "Artifact",
    "ProviderConnection",
    "AgentDefinition",
    "init_db",
    "get_session",
    "get_engine",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tabel inti run konsensus
# ---------------------------------------------------------------------------


class Run(SQLModel, table=True):
    """Satu run konsensus MUFAKAT."""

    __tablename__ = "runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, unique=True, description="ID run, mis. run-2026-11-20-001.")
    project_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="running", description="running | passed | failed | aborted.")
    task: str = Field(default="", description="Deskripsi tugas yang dikerjakan run ini.")
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Message(SQLModel, table=True):
    """Satu pesan konsensus yang tersimpan (cermin MufakatMessage)."""

    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    round: int = Field(default=1, ge=1)
    phase: str = Field(default="research")
    agent_id: str = Field(default="")
    role: str = Field(default="")
    model_family: str = Field(default="other")
    stance: Optional[str] = Field(default=None)
    content_json: str = Field(default="{}", description="Isi pesan sebagai JSON.")
    created_at: datetime = Field(default_factory=_now)


class GateResult(SQLModel, table=True):
    """Hasil satu gate verifikasi (tests, lint, semgrep, dsb.) pada run."""

    __tablename__ = "gate_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    gate: str = Field(default="", description="Nama gate, mis. tests / semgrep / bandit.")
    passed: bool = Field(default=False)
    detail: str = Field(default="", description="Ringkasan hasil gate.")
    created_at: datetime = Field(default_factory=_now)


class UsageLedger(SQLModel, table=True):
    """Catatan pemakaian token / biaya per agent per run."""

    __tablename__ = "usage_ledger"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    agent_id: str = Field(default="")
    model: str = Field(default="")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Entitas kolaborasi (ChatGPT)
# ---------------------------------------------------------------------------


class Project(SQLModel, table=True):
    """Proyek tempat run, task, dan meeting dikelompokkan."""

    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=_now)


class Task(SQLModel, table=True):
    """Tugas di dalam proyek, dikerjakan lewat satu atau beberapa run."""

    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: Optional[int] = Field(default=None, foreign_key="projects.id")
    title: str = Field(default="")
    description: str = Field(default="")
    status: str = Field(default="open", description="open | in_progress | done | blocked.")
    created_at: datetime = Field(default_factory=_now)


class Meeting(SQLModel, table=True):
    """Satu sesi debat / meeting multi-agent untuk sebuah tugas."""

    __tablename__ = "meetings"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id")
    title: str = Field(default="")
    status: str = Field(default="open", description="open | closed | aborted.")
    created_at: datetime = Field(default_factory=_now)


class MeetingRound(SQLModel, table=True):
    """Satu ronde dalam sebuah meeting."""

    __tablename__ = "meeting_rounds"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id")
    round_no: int = Field(default=1, ge=1)
    phase: str = Field(default="research")
    created_at: datetime = Field(default_factory=_now)


class Decision(SQLModel, table=True):
    """Keputusan hasil konsensus pada sebuah meeting."""

    __tablename__ = "decisions"

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: Optional[int] = Field(default=None, foreign_key="meetings.id")
    summary: str = Field(default="")
    verdict: str = Field(default="", description="approve | reject | revise.")
    created_at: datetime = Field(default_factory=_now)


class DecisionDissent(SQLModel, table=True):
    """Pendapat berbeda (dissent) terhadap sebuah keputusan."""

    __tablename__ = "decision_dissents"

    id: Optional[int] = Field(default=None, primary_key=True)
    decision_id: Optional[int] = Field(default=None, foreign_key="decisions.id")
    agent_id: str = Field(default="")
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=_now)


class Approval(SQLModel, table=True):
    """Persetujuan manusia / reviewer atas keputusan atau artefak."""

    __tablename__ = "approvals"

    id: Optional[int] = Field(default=None, primary_key=True)
    decision_id: Optional[int] = Field(default=None, foreign_key="decisions.id")
    approver: str = Field(default="")
    approved: bool = Field(default=False)
    note: str = Field(default="")
    created_at: datetime = Field(default_factory=_now)


class AuditLog(SQLModel, table=True):
    """Jejak audit atas aksi penting (run, keputusan, persetujuan)."""

    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str = Field(default="")
    action: str = Field(default="")
    target_type: str = Field(default="")
    target_id: str = Field(default="")
    detail: str = Field(default="")
    created_at: datetime = Field(default_factory=_now)


class Artifact(SQLModel, table=True):
    """Artefak yang dihasilkan run (kode, spec, laporan, dsb.)."""

    __tablename__ = "artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(default="", index=True)
    kind: str = Field(default="", description="spec | code | test | report | patch.")
    path: str = Field(default="", description="Jalur relatif artefak di dalam run.")
    created_at: datetime = Field(default_factory=_now)


class ProviderConnection(SQLModel, table=True):
    """Koneksi provider yang terdaftar (nama + env key, tanpa menyimpan secret)."""

    __tablename__ = "provider_connections"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="", unique=True)
    kind: str = Field(default="api", description="api | cli.")
    env_key: str = Field(default="", description="Nama variabel env kunci, bukan nilainya.")
    base_url: str = Field(default="")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_now)


class AgentDefinition(SQLModel, table=True):
    """Definisi agent: peran, provider, dan model yang dipakai."""

    __tablename__ = "agent_definitions"

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_id: str = Field(default="", unique=True)
    role: str = Field(default="")
    provider: str = Field(default="")
    model: str = Field(default="")
    created_at: datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Fungsi bantu engine / sesi
# ---------------------------------------------------------------------------


def get_engine(path: str | Path):
    """Buat engine SQLite untuk ``path`` (file dibuat bila belum ada)."""
    db_path = Path(path)
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def init_db(path: str | Path):
    """Buat semua tabel bila belum ada; kembalikan engine yang dipakai."""
    engine = get_engine(path)
    SQLModel.metadata.create_all(engine)
    return engine


def get_session(path: str | Path) -> Session:
    """Kembalikan sesi SQLModel baru untuk database di ``path``.

    Pemanggil bertanggung jawab menutup sesi (atau memakai ``with``).
    """
    engine = get_engine(path)
    SQLModel.metadata.create_all(engine)
    return Session(engine)
