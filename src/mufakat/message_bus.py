"""Message bus dalam-memori MUFAKAT (A2A antar-agent).

Bus ini dipakai untuk pertukaran pesan antar-agent di dalam satu proses:
setiap pesan dibungkus :class:`Envelope` berisi identitas percakapan,
pengirim, penerima, dan muatan (payload) bebas.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

__all__ = ["Envelope", "InMemoryMessageBus"]


@dataclass
class Envelope:
    """Amplop pesan antar-agent."""

    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = ""
    project_id: str = ""
    sender_agent_id: str = ""
    recipient_agent_id: str = ""
    message_type: str = ""
    correlation_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validasi ringan ala Pydantic: field identitas wajib terisi."""
        if not self.conversation_id:
            raise ValueError("conversation_id wajib diisi.")
        if not self.sender_agent_id:
            raise ValueError("sender_agent_id wajib diisi.")
        if not self.message_type:
            raise ValueError("message_type wajib diisi.")
        if not isinstance(self.payload, dict):
            raise TypeError("payload harus berupa dict.")


class InMemoryMessageBus:
    """Bus pesan dalam-memori dengan publish/subscribe per percakapan."""

    def __init__(self) -> None:
        self._messages: list[Envelope] = []
        self._subscribers: dict[str, list[Callable[[Envelope], None]]] = defaultdict(list)

    def publish(self, envelope: Envelope) -> Envelope:
        """Simpan amplop dan teruskan ke semua subscriber percakapannya."""
        self._messages.append(envelope)
        for handler in list(self._subscribers.get(envelope.conversation_id, [])):
            handler(envelope)
        return envelope

    def subscribe(
        self, conversation_id: str, handler: Callable[[Envelope], None]
    ) -> Callable[[], None]:
        """Daftarkan ``handler`` untuk satu ``conversation_id``.

        Mengembalikan fungsi ``unsubscribe`` untuk melepas langganan.
        """
        self._subscribers[conversation_id].append(handler)

        def unsubscribe() -> None:
            handlers = self._subscribers.get(conversation_id, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def list_by_conversation(self, conversation_id: str) -> list[Envelope]:
        """Kembalikan semua amplop pada satu percakapan, urut waktu dibuat."""
        return [m for m in self._messages if m.conversation_id == conversation_id]

    def list_all(self) -> list[Envelope]:
        """Kembalikan semua amplop yang pernah diterbitkan."""
        return list(self._messages)
