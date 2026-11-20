"""Cache & queue MUFAKAT — Redis opsional, fallback in-memory.

Jujur: bila ``REDIS_URL`` diset DAN pustaka ``redis`` terpasang DAN
server Redis bisa dijangkau, cache/queue memakai Redis. Bila salah
satu syarat tidak terpenuhi, dipakai fallback in-memory (dict +
list) dan ``backend`` dilaporkan sebagai ``"memory"`` — tidak ada
klaim Redis bila sebenarnya tidak dipakai. Cache tidak pernah
menyimpan secret; queue hanya menyimpan payload JSON-able.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


class Cache:
    """Cache key-value dengan TTL (detik)."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.backend = "memory"
        self._client = None
        self._store: dict[str, tuple[Any, float | None]] = {}
        url = redis_url or os.environ.get("REDIS_URL", "").strip()
        if url:
            try:
                import redis  # type: ignore

                client = redis.Redis.from_url(url, socket_connect_timeout=2,
                                              socket_timeout=2)
                client.ping()
                self._client = client
                self.backend = "redis"
            except Exception:
                self._client = None
                self.backend = "memory"

    def get(self, key: str) -> Any | None:
        """Ambil nilai; None bila tidak ada / sudah kedaluwarsa."""
        if self._client is not None:
            raw = self._client.get(key)
            return json.loads(raw) if raw is not None else None
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Simpan nilai dengan TTL opsional (detik)."""
        if self._client is not None:
            self._client.set(key, json.dumps(value), ex=ttl)
            return
        expires_at = time.time() + ttl if ttl else None
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        """Hapus satu key."""
        if self._client is not None:
            self._client.delete(key)
            return
        self._store.pop(key, None)


class Queue:
    """Queue FIFO sederhana (daftar tugas JSON-able)."""

    def __init__(self, redis_url: str | None = None,
                 name: str = "mufakat:queue") -> None:
        self.backend = "memory"
        self.name = name
        self._client = None
        self._items: list[Any] = []
        url = redis_url or os.environ.get("REDIS_URL", "").strip()
        if url:
            try:
                import redis  # type: ignore

                client = redis.Redis.from_url(url, socket_connect_timeout=2,
                                              socket_timeout=2)
                client.ping()
                self._client = client
                self.backend = "redis"
            except Exception:
                self._client = None
                self.backend = "memory"

    def enqueue(self, item: Any) -> None:
        """Tambahkan item ke ujung queue."""
        if self._client is not None:
            self._client.rpush(self.name, json.dumps(item))
            return
        self._items.append(item)

    def dequeue(self) -> Any | None:
        """Ambil item dari depan queue; None bila kosong."""
        if self._client is not None:
            raw = self._client.lpop(self.name)
            if raw is None:
                return None
            if isinstance(raw, (str, bytes, bytearray)):
                return json.loads(raw)
            return None
        if not self._items:
            return None
        return self._items.pop(0)

    def __len__(self) -> int:
        if self._client is not None:
            return int(self._client.llen(self.name))
        return len(self._items)
