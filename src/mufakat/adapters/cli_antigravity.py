"""Google Antigravity CLI adapter (T4)."""

from __future__ import annotations

from ._cli import check_binary, run_cli
from .base import Adapter, Reply


class AntigravityAdapter(Adapter):
    """Adapter over the ``agy`` CLI (Antigravity)."""

    name = "antigravity"
    family = "antigravity"

    def __init__(self, name: str = "antigravity",
                 family: str = "antigravity"):
        self.name = name
        self.family = family

    def is_available(self) -> bool:
        return check_binary("agy")

    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await run_cli(
            self.name, self.family,
            ["agy", "-p", "--output-format", "json", "--", full_prompt], ctx)
