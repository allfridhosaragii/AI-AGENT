"""Node spec (T7): tulis spesifikasi dari ide + hasil debat.

Tanpa adapter: spec.md dummy deterministik berbahasa Indonesia.
Bila ``ctx["worktree"]`` ada, spec.md juga ditulis ke worktree.
"""

from __future__ import annotations

from pathlib import Path

try:
    from .common import append_message, call_adapter
except ImportError:  # pragma: no cover
    from common import append_message, call_adapter  # type: ignore


def render_spec(idea: str) -> str:
    return (
        "# Spesifikasi (spec.md)\n\n"
        f"## Ide\n{idea}\n\n"
        "## Tujuan\nMembangun solusi yang sederhana, teruji, dan mudah dirawat "
        "sesuai hasil mufakat debat.\n\n"
        "## Ruang Lingkup\n"
        "- Fitur inti sesuai ide di atas.\n"
        "- Di luar lingkup: fitur tambahan yang belum disepakati.\n\n"
        "## Kriteria Penerimaan\n"
        "- Semua gate verifikasi lolos (semgrep, bandit, gitleaks, "
        "trivy, pytest, lint).\n"
        "- Review menyetujui dengan rasio minimal 2/3.\n"
    )


async def node(state, adapters=None, ctx=None):
    """Spesifikasi -> patch state (dan spec.md di worktree bila ada)."""
    idea = getattr(state, "idea", "")
    text = await call_adapter(adapters, "spec", render_spec(idea), state)
    worktree = (ctx or {}).get("worktree")
    if worktree:
        try:
            Path(worktree).mkdir(parents=True, exist_ok=True)
            Path(worktree, "spec.md").write_text(text, encoding="utf-8")
        except OSError:
            pass
    messages = append_message(state, "spec", "Spesifikasi ditulis (spec.md).")
    return {"messages": messages, "spec": text, "phase": "code",
            "approved_spec": True}
