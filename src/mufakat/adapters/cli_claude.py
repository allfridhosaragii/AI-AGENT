"""Claude CLI adapter (T4)."""

from __future__ import annotations

from ._cli import check_binary, run_cli
from .base import Adapter, Reply


class ClaudeAdapter(Adapter):
    """Adapter over the ``claude`` CLI (``claude -p --output-format json``)."""

    name = "claude"
    family = "claude"

    def __init__(self, name: str = "claude", family: str = "claude"):
        self.name = name
        self.family = family

    def is_available(self) -> bool:
        return check_binary("claude")

    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await run_cli(
            self.name, self.family,
            ["claude", "-p", "--output-format", "json", full_prompt], ctx)
