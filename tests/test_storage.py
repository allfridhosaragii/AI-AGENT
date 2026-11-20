"""Test storage opsional MUFAKAT: Postgres + Redis + fallback.

- Default tetap SQLite (tanpa DATABASE_URL / REDIS_URL).
- DATABASE_URL Postgres: engine dibuat tanpa koneksi langsung;
  bila driver psycopg tidak ada, error-nya jelas (bukan fallback
  diam-diam ke SQLite).
- Cache/Queue: bila Redis tidak bisa dijangkau, backend dilaporkan
  ``memory`` dan operasi tetap jalan (fallback in-memory).
"""

from __future__ import annotations

import time

import pytest

from mufakat.storage.cache import Cache, Queue
from mufakat.storage.db import (
    Run,
    get_engine_for_url,
    init_db,
    resolve_database_url,
)


def test_resolve_database_url_default_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MUFAKAT_DB", raising=False)
    assert resolve_database_url() == "sqlite:///./runs/mufakat.db"


def test_resolve_database_url_prioritas_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    assert resolve_database_url() == "postgresql://u:p@h:5432/db"


def test_resolve_database_url_mufakat_db_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MUFAKAT_DB", "/tmp/x.db")
    assert resolve_database_url() == "sqlite:////tmp/x.db"


def test_get_engine_for_url_sqlite_dan_init_db(tmp_path):
    path = tmp_path / "test.db"
    engine = get_engine_for_url(f"sqlite:///{path}")
    assert engine is not None
    init_db(path)
    assert path.is_file()
    # Tabel runs ada dan bisa dipakai.
    from sqlmodel import Session, select

    with Session(engine) as session:
        session.add(Run(run_id="r1", status="running", task="tes"))
        session.commit()
        rows = session.exec(select(Run)).all()
        assert len(rows) == 1 and rows[0].run_id == "r1"


def test_get_engine_for_url_postgres_tanpa_driver_error_jelas(monkeypatch):
    # Bila psycopg terpasang, engine Postgres dibuat (lazy, tanpa
    # koneksi). Bila tidak terpasang, RuntimeError yang jelas.
    try:
        import psycopg  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="psycopg"):
            get_engine_for_url("postgresql://u:p@h:5432/db")
        return
    engine = get_engine_for_url("postgresql://u:p@h:5432/db")
    assert engine is not None


def test_get_engine_for_url_skema_tidak_dikenal():
    with pytest.raises(ValueError):
        get_engine_for_url("mysql://u:p@h/db")


def test_cache_fallback_memory_tanpa_redis():
    cache = Cache(redis_url="redis://localhost:6399/0")
    assert cache.backend == "memory"
    cache.set("k", {"a": 1}, ttl=60)
    assert cache.get("k") == {"a": 1}
    cache.delete("k")
    assert cache.get("k") is None


def test_cache_ttl_kedaluwarsa():
    cache = Cache()
    assert cache.backend == "memory"
    cache.set("k", "v", ttl=1)
    assert cache.get("k") == "v"
    time.sleep(1.1)
    assert cache.get("k") is None


def test_queue_fallback_memory_fifo():
    queue = Queue(redis_url="redis://localhost:6399/0")
    assert queue.backend == "memory"
    assert len(queue) == 0
    assert queue.dequeue() is None
    queue.enqueue({"task": 1})
    queue.enqueue({"task": 2})
    assert len(queue) == 2
    assert queue.dequeue() == {"task": 1}
    assert queue.dequeue() == {"task": 2}
    assert queue.dequeue() is None
