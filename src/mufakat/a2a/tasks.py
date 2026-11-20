"""Task / Message / Artifact A2A (format sesuai spesifikasi A2A).

Task adalah unit kerja yang dikirim ke agent; Message adalah
pesan dengan role (user/agent) dan parts; Artifact adalah hasil
kerja (mis. teks, file, patch) yang dihasilkan task.

Dispatcher di sini bersifat LOKAL (in-process): handler didaftarkan
per nama agent, dan ``dispatch_task`` memanggil handler itu.
Tidak ada transport HTTP JSON-RPC ke agent eksternal — interop
eksternal belum terverifikasi.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    """Status task A2A."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
    REJECTED = "rejected"


class Part(BaseModel):
    """Satu bagian pesan/artefak (teks atau data)."""

    kind: str = "text"
    text: str = ""
    data: dict = Field(default_factory=dict)


class Message(BaseModel):
    """Pesan A2A: role + parts + konteks."""

    message_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    role: str = "user"
    parts: list[Part] = Field(default_factory=list)
    context_id: str = ""
    task_id: str = ""

    def text(self) -> str:
        """Gabungan teks semua part."""
        return "\n".join(p.text for p in self.parts if p.text)


class Artifact(BaseModel):
    """Hasil kerja sebuah task."""

    artifact_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    parts: list[Part] = Field(default_factory=list)


class TaskStatus(BaseModel):
    """Status task saat ini."""

    state: TaskState = TaskState.SUBMITTED
    message: Message | None = None
    timestamp: str = ""


class Task(BaseModel):
    """Task A2A: dikirim ke agent, menghasilkan artifact."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    context_id: str = ""
    status: TaskStatus = Field(default_factory=TaskStatus)
    artifacts: list[Artifact] = Field(default_factory=list)
    history: list[Message] = Field(default_factory=list)

    def add_artifact(self, artifact: Artifact) -> None:
        """Tambahkan artifact hasil kerja ke task."""
        self.artifacts.append(artifact)


_HANDLERS: dict[str, Callable[[Task], Task]] = {}


def register_handler(agent_name: str,
                     handler: Callable[[Task], Task]) -> None:
    """Daftarkan handler lokal untuk satu nama agent."""
    _HANDLERS[agent_name] = handler


def create_task(context_id: str, message: Message) -> Task:
    """Buat task baru dari satu pesan user."""
    task = Task(context_id=context_id, history=[message])
    message.task_id = task.id
    return task


def dispatch_task(task: Task, agent_name: str) -> Task:
    """Kirim task ke handler lokal agent; tandai completed/failed.

    Bila tidak ada handler terdaftar untuk ``agent_name``, task
    ditandai ``failed`` dengan pesan yang jelas — bukan pura-pura
    berhasil.
    """
    handler = _HANDLERS.get(agent_name)
    if handler is None:
        task.status = TaskStatus(
            state=TaskState.FAILED,
            message=Message(role="agent", parts=[Part(
                text=f"Tidak ada handler lokal untuk agent '{agent_name}'. "
                     "Interop A2A eksternal belum terverifikasi.")]))
        return task
    task.status = TaskStatus(state=TaskState.WORKING)
    try:
        result = handler(task)
    except Exception as exc:  # noqa: BLE001 — kegagalan handler = task gagal
        task.status = TaskStatus(
            state=TaskState.FAILED,
            message=Message(role="agent", parts=[Part(text=str(exc))]))
        return task
    result.status = TaskStatus(state=TaskState.COMPLETED)
    return result
