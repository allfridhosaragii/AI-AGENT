"""OpenCode CLI adapter (T4)."""

from __future__ import annotations

from ._cli import check_binary, run_cli
from .base import Adapter, Reply


class OpenCodeAdapter(Adapter):
    """Adapter over the ``opencode`` CLI (``opencode run <prompt>``)."""

    name = "opencode"
    family = "opencode"

    def __init__(self, name: str = "opencode", family: str = "opencode"):
        self.name = name
        self.family = family

    def is_available(self) -> bool:
        return check_binary("opencode")

    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await run_cli(
            self.name, self.family, ["opencode", "run", full_prompt], ctx)
