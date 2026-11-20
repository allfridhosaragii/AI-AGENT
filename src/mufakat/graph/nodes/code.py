"""Node code (T7+T11): tulis implementasi nyata ke worktree.

Perilaku jujur:
- Bila adapter ``code`` tersedia (API key / CLI login), teks
  implementasi diminta ke adapter itu; bila adapter mengembalikan
  kode Python yang mengandung ``FastAPI``, kode itu dipakai sebagai
  ``main.py``. Bila tidak, dipakai template deterministik di bawah.
- Bila tidak ada adapter sama sekali, template deterministik yang
  dipakai — dan itu dicatat di pesan node (bukan diklaim sebagai
  hasil AI).
- Selalu menulis DUA file ke worktree: ``main.py`` (REST API todo
  FastAPI) dan ``test_main.py`` (test TestClient-nya), sehingga
  node audit/test sesudahnya benar-benar menjalankan gate atas
  kode yang dihasilkan, bukan atas teks ringkasan.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    from .common import append_message, call_adapter, sha256_text
except ImportError:  # pragma: no cover
    from common import append_message, call_adapter, sha256_text  # type: ignore

TEMPLATE_MAIN = '''"""REST API todo (FastAPI) — hasil pipeline MUFAKAT."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Todo API")


class TodoCreate(BaseModel):
    """Payload pembuatan todo."""

    title: str = Field(..., min_length=1)
    done: bool = False


class Todo(TodoCreate):
    """Todo yang tersimpan."""

    id: int


_TODOS: dict[int, Todo] = {}
_NEXT_ID = 1


@app.get("/todos", response_model=list[Todo])
def list_todos() -> list[Todo]:
    """Daftar semua todo."""
    return list(_TODOS.values())


@app.post("/todos", response_model=Todo, status_code=201)
def create_todo(payload: TodoCreate) -> Todo:
    """Buat todo baru."""
    global _NEXT_ID
    todo = Todo(id=_NEXT_ID, **payload.model_dump())
    _TODOS[_NEXT_ID] = todo
    _NEXT_ID += 1
    return todo


@app.get("/todos/{todo_id}", response_model=Todo)
def get_todo(todo_id: int) -> Todo:
    """Ambil satu todo berdasarkan id."""
    todo = _TODOS.get(todo_id)
    if todo is None:
        raise HTTPException(status_code=404, detail="Todo tidak ditemukan.")
    return todo


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int) -> None:
    """Hapus satu todo berdasarkan id."""
    if todo_id not in _TODOS:
        raise HTTPException(status_code=404, detail="Todo tidak ditemukan.")
    del _TODOS[todo_id]
'''

TEMPLATE_TEST = '''"""Test REST API todo hasil pipeline MUFAKAT."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_create_and_list_todos():
    res = client.post("/todos", json={"title": "Belajar MUFAKAT"})
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Belajar MUFAKAT"
    assert created["done"] is False
    res = client.get("/todos")
    assert res.status_code == 200
    assert any(t["id"] == created["id"] for t in res.json())


def test_get_todo_not_found():
    assert client.get("/todos/9999").status_code == 404


def test_delete_todo():
    created = client.post("/todos", json={"title": "Hapus saya"}).json()
    assert client.delete(f"/todos/{created['id']}").status_code == 204
    assert client.get(f"/todos/{created['id']}").status_code == 404
'''


def _extract_python(text: str) -> str | None:
    """Ambil blok kode python dari teks adapter (fence ```python)."""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    candidate = match.group(1) if match else text
    if "FastAPI" in candidate and "def " in candidate:
        return candidate.strip() + "\n"
    return None


async def node(state, adapters=None, ctx=None):
    """Tulis main.py + test_main.py ke worktree -> patch state."""
    code = await call_adapter(adapters, "code", TEMPLATE_MAIN, state)
    extracted = _extract_python(code) if code != TEMPLATE_MAIN else None
    main_code = extracted or TEMPLATE_MAIN
    used_adapter = extracted is not None
    worktree = (ctx or {}).get("worktree")
    files = {"main.py": main_code, "test_main.py": TEMPLATE_TEST}
    if worktree:
        try:
            root = Path(worktree)
            root.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (root / name).write_text(content, encoding="utf-8")
            (ctx or {})["generated_files"] = sorted(files)
        except OSError:
            pass
    source = "adapter" if used_adapter else "template deterministik (mock)"
    messages = append_message(
        state, "coder",
        f"Implementasi ditulis dari {source}: main.py + test_main.py "
        f"({len(main_code)} karakter main.py).")
    combined = "".join(files[name] for name in sorted(files))
    return {"messages": messages, "phase": "review",
            "diff_hash": sha256_text(combined),
            "total_iterations": getattr(state, "total_iterations", 0) + 1}
