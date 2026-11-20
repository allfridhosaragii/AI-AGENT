"""Node code (T7): tulis file contoh implementasi.

Tanpa adapter: file contoh dummy deterministik (``main.py``) yang
aman — tanpa pola SQL injection, eval, atau secret. Bila
``ctx["worktree"]`` ada, file ditulis ke sana; bila tidak, hanya
dicatat di messages.
"""

from __future__ import annotations

from pathlib import Path

try:
    from .common import append_message, call_adapter, sha256_text
except ImportError:  # pragma: no cover
    from common import append_message, call_adapter, sha256_text  # type: ignore

EXAMPLE_CODE = '''"""Contoh implementasi hasil mufakat — aman, tanpa pola berbahaya."""

import sqlite3


def get_user(conn: sqlite3.Connection, user_id: int):
    """Ambil pengguna dengan query berparameter (aman dari SQL injection)."""
    cur = conn.execute("SELECT id, name FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def main() -> None:
    print("Contoh aplikasi MUFAKAT berjalan.")


if __name__ == "__main__":
    main()
'''


async def node(state, adapters=None, ctx=None):
    """Tulis contoh kode -> patch state (diff_hash dari isi file)."""
    code = await call_adapter(adapters, "code", EXAMPLE_CODE, state)
    worktree = (ctx or {}).get("worktree")
    if worktree:
        try:
            Path(worktree).mkdir(parents=True, exist_ok=True)
            Path(worktree, "main.py").write_text(code, encoding="utf-8")
        except OSError:
            pass
    messages = append_message(state, "coder", "File contoh main.py ditulis.")
    return {"messages": messages, "phase": "review",
            "diff_hash": sha256_text(code),
            "total_iterations": getattr(state, "total_iterations", 0) + 1}
