"""Muse Codex CLI adapter (T4)."""

from __future__ import annotations

from ._cli import check_binary, run_cli
from .base import Adapter, Reply


class CodexAdapter(Adapter):
    """Adapter over the ``codex`` CLI (``codex exec --json``)."""

    name = "codex"
    family = "codex"

    def __init__(self, name: str = "codex", family: str = "codex"):
        self.name = name
        self.family = family

    def is_available(self) -> bool:
        return check_binary("codex", ["codex", "login", "status"], timeout=5)

    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await run_cli(
            self.name, self.family,
            ["codex", "exec", "--json", "--", full_prompt], ctx)
