"""Domain communication — pesan antar-agent via message bus internal.

Permission: ``read`` untuk membaca thread, ``write-sandbox`` untuk
mengirim pesan. Pesan TIDAK dikirim ke agent eksternal; ini bus
dalam-proses (lihat ``mufakat.message_bus``). Interop A2A eksternal
belum terverifikasi — lihat ``mufakat.a2a``.
"""

from __future__ import annotations

from mufakat.mcp_server.tools import err, ok
from mufakat.message_bus import Envelope
from mufakat.runner import utcnow

from . import store

DOMAIN = "communication"

CONTRACTS = [
    {"name": "agent_send_message",
     "description": "Kirim pesan antar-agent di bus internal.",
     "permission": "write-sandbox", "scope": "messages"},
    {"name": "message_list",
     "description": "Daftar pesan pada satu conversation_id.",
     "permission": "read", "scope": "messages"},
]


def agent_send_message(conversation_id: str, sender_agent_id: str,
                       recipient_agent_id: str, message_type: str,
                       payload: str = "") -> dict:
    """Kirim pesan antar-agent (envelope internal, bukan A2A eksternal)."""
    import json

    try:
        data = json.loads(payload) if payload else {}
        if not isinstance(data, dict):
            raise ValueError("payload harus objek JSON.")
    except ValueError as exc:
        return err(f"payload bukan JSON objek: {exc}")
    try:
        envelope = Envelope(
            conversation_id=conversation_id,
            sender_agent_id=sender_agent_id,
            recipient_agent_id=recipient_agent_id,
            message_type=message_type,
            payload=data,
        )
    except (ValueError, TypeError) as exc:
        return err(str(exc))
    store.bus.publish(envelope)
    return ok(message_id=envelope.message_id,
              conversation_id=conversation_id,
              sender_agent_id=sender_agent_id,
              recipient_agent_id=recipient_agent_id,
              message_type=message_type, created_at=utcnow())


def message_list(conversation_id: str) -> dict:
    """Daftar pesan pada satu conversation_id (urut waktu dibuat)."""
    items = store.bus.list_by_conversation(conversation_id)
    return ok(conversation_id=conversation_id, count=len(items), items=[
        {"message_id": m.message_id, "sender_agent_id": m.sender_agent_id,
         "recipient_agent_id": m.recipient_agent_id,
         "message_type": m.message_type, "payload": m.payload,
         "created_at": m.created_at.isoformat()}
        for m in items
    ])


def register(mcp) -> list[str]:
    """Daftarkan semua tool domain communication ke ``mcp``."""
    for fn in (agent_send_message, message_list):
        mcp.tool(fn)
    return [c["name"] for c in CONTRACTS]
