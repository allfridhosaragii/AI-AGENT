"""Rate limiting / quota (T5): token bucket + per-provider quotas."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class TokenBucket:
    """Token bucket rate limiter.

    ``capacity`` tokens max; refills at ``refill_per_minute`` tokens/min.
    ``allow(n)`` consumes *n* tokens iff enough are available.
    """

    def __init__(self, capacity: int, refill_per_minute: float):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if refill_per_minute < 0:
            raise ValueError("refill_per_minute must be >= 0")
        self.capacity = float(capacity)
        self.refill_per_minute = float(refill_per_minute)
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed_min = (now - self._last_refill) / 60.0
        if elapsed_min > 0:
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed_min * self.refill_per_minute,
            )
            self._last_refill = now

    def allow(self, n: int = 1) -> bool:
        if n <= 0:
            return True
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class QuotaManager:
    """Per-provider RPM/RPD quotas backed by TokenBuckets.

    ``config``: ``{provider: {"rpm": int, "rpd": int}}``.  Missing keys
    mean unlimited for that dimension.  ``record`` logs usage and,
    when ``db_path`` is given, persists a row to a SQLite ``usage_ledger``.
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS usage_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            provider TEXT NOT NULL,
            tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0
        )
    """

    def __init__(self, config: dict | None = None, db_path: str | None = None):
        self.config = config or {}
        self._buckets: dict[str, TokenBucket] = {}
        self._daily: dict[str, TokenBucket] = {}
        for provider, limits in self.config.items():
            rpm = limits.get("rpm")
            rpd = limits.get("rpd")
            if rpm is not None:
                self._buckets[provider] = TokenBucket(
                    capacity=int(rpm), refill_per_minute=float(rpm))
            if rpd is not None:
                self._daily[provider] = TokenBucket(
                    capacity=int(rpd), refill_per_minute=float(rpd) / 1440.0)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.execute(self._SCHEMA)
            self._conn.commit()

    def allow(self, provider: str) -> bool:
        """Consume one request slot for *provider* (RPM and RPD)."""
        minute = self._buckets.get(provider)
        if minute is not None and not minute.allow(1):
            return False
        day = self._daily.get(provider)
        if day is not None and not day.allow(1):
            return False
        return True

    def record(self, provider: str, tokens: int, cost: float) -> None:
        """Log usage for *provider* to the SQLite ledger (if configured)."""
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO usage_ledger (ts, provider, tokens, cost_usd)"
            " VALUES (?, ?, ?, ?)",
            (time.time(), provider, int(tokens), float(cost)),
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
