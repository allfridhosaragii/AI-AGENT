"""Build graph MUFAKAT (T7).

Bila langgraph tersedia: StateGraph nyata dengan conditional edges
dari ``graph/edges.py`` dan checkpointer SQLite bila path diberikan.
Bila langgraph TIDAK tersedia: kembalikan ``SimpleGraph`` fallback
yang menjalankan research -> debate -> critique -> meeting -> spec
secara sekuensial, agar demo tetap jalan. Modul ini tidak pernah
gagal import hanya karena langgraph belum terinstal.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .edges import should_continue_debate, should_revise
from .nodes import NODES
from .state import RunState

_NODE_ORDER = ["research", "debate", "critique", "meeting", "spec",
               "code", "review", "audit", "test", "revise"]


def _apply_patch(state: RunState, patch: dict) -> RunState:
    if not patch:
        return state
    if hasattr(state, "model_copy"):
        return state.model_copy(update=patch)
    data = state.to_dict() if hasattr(state, "to_dict") else dict(state)
    data.update(patch)
    return RunState(**data)


def _coerce_state(data) -> RunState:
    if isinstance(data, RunState):
        return data
    if isinstance(data, dict):
        return RunState.from_dict(data)
    raise TypeError(f"state harus RunState atau dict, bukan {type(data)!r}")


class SimpleGraph:
    """Fallback tanpa langgraph: jalankan node demo secara sekuensial."""

    def __init__(self, adapters=None, nodes=None, ctx=None):
        self.adapters = adapters
        self.nodes = nodes or NODES
        self.ctx = dict(ctx or {})

    async def ainvoke(self, state, ctx=None):
        current = _coerce_state(state)
        ctx = dict(ctx or {}) or self.ctx
        # Demo: research -> debate -> critique -> meeting -> spec.
        for name in ["research", "debate", "critique", "meeting", "spec"]:
            patch = await self.nodes[name](current, self.adapters, ctx)
            current = _apply_patch(current, patch)
        return current.to_dict()

    def invoke(self, state, ctx=None):
        return asyncio.run(self.ainvoke(state, ctx))


def build_graph(adapters=None, checkpointer_path=None, ctx=None):
    """Bangun graph; kembalikan StateGraph langgraph atau SimpleGraph.

    ``ctx`` dipakai bersama (satu dict yang sama) oleh semua node:
    di sinilah ``worktree``, ``run_dir``, dan ``gate_results``
    dibagikan antar-node (audit -> test -> revise). Tanpa ctx
    bersama, hasil audit tidak pernah sampai ke node test.
    """
    shared_ctx = {"adapters": adapters, **(ctx or {})}
    try:
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return SimpleGraph(adapters=adapters, ctx=shared_ctx)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:  # paket langgraph-checkpoint-sqlite belum terpasang
        SqliteSaver = None  # type: ignore

    graph = StateGraph(RunState)
    for name in _NODE_ORDER:
        fn = NODES[name]

        def _wrap(fn=fn, adapters=adapters, shared_ctx=shared_ctx):
            async def _node(state: RunState):
                patch = await fn(state, adapters, shared_ctx)
                return patch
            return _node

        graph.add_node(name, _wrap())

    graph.add_edge(START, "research")
    graph.add_edge("research", "debate")
    graph.add_edge("debate", "critique")
    graph.add_edge("critique", "meeting")
    graph.add_conditional_edges("meeting", should_continue_debate, {
        "debate": "debate",
        "spec": "spec",
        "escalate": END,
    })
    graph.add_edge("spec", "code")
    graph.add_edge("code", "review")
    graph.add_edge("review", "audit")
    graph.add_edge("audit", "test")
    graph.add_conditional_edges("test", should_revise, {
        "revise": "revise",
        "audit_final": END,
        "escalate": END,
    })
    graph.add_edge("revise", "review")

    checkpointer: Any = None
    if checkpointer_path and SqliteSaver is not None:
        # M10: SqliteSaver.from_conn_string() mengembalikan context
        # manager (crash "Invalid checkpointer provided"). Pakai
        # konstruktor langsung dengan koneksi — BUKAN from_conn_string.
        # Graph MUFAKAT dijalankan async (ainvoke): SqliteSaver sinkron
        # tidak mendukung metode async, jadi bila ada event loop yang
        # sedang berjalan, pakai AsyncSqliteSaver dengan koneksi
        # aiosqlite (dibuat di loop yang sama — AsyncSqliteSaver
        # terikat ke loop pembuatnya). Bila dipanggil dari konteks
        # sinkron (tanpa loop), pakai SqliteSaver(sqlite3.connect(
        # path, check_same_thread=False)) sesuai audit — graph itu
        # lalu harus dibangun/dijalankan di dalam loop async bila
        # memakai ainvoke.
        import asyncio

        try:
            asyncio.get_running_loop()
            _loop_running = True
        except RuntimeError:
            _loop_running = False
        if _loop_running:
            try:
                import aiosqlite
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                checkpointer = AsyncSqliteSaver(
                    aiosqlite.connect(str(checkpointer_path)))
            except Exception:
                checkpointer = MemorySaver()
        else:
            import sqlite3

            try:
                conn = sqlite3.connect(str(checkpointer_path),
                                       check_same_thread=False)
                checkpointer = SqliteSaver(conn)
            except Exception:
                checkpointer = MemorySaver()
    else:
        checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
