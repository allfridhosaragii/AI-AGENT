"""A2A minimal MUFAKAT — Agent Card + Task/artifact envelope.

Jujur: modul ini mengimplementasikan **format** protokol A2A
(Agent Card, Task, Message, Artifact — sesuai A2A spec) dan
pengiriman task antar-agent **di dalam proses** (dispatcher lokal).
Interoperabilitas dengan agent A2A **eksternal** (HTTP JSON-RPC
ke server agent lain) BELUM terverifikasi — tidak ada server A2A
eksternal yang diuji di sini, dan modul ini tidak mengklaimnya.
Untuk komunikasi internal, pakai ``mufakat.message_bus``.
"""

from __future__ import annotations

from .card import AgentCapability, AgentCard, AgentSkill, create_agent_card
from .tasks import (
    Artifact,
    Message,
    Part,
    Task,
    TaskState,
    TaskStatus,
    create_task,
    dispatch_task,
    register_handler,
)

__all__ = [
    "AgentCard", "AgentCapability", "AgentSkill", "create_agent_card",
    "Artifact", "Message", "Part", "Task", "TaskState", "TaskStatus",
    "create_task", "dispatch_task", "register_handler",
]
