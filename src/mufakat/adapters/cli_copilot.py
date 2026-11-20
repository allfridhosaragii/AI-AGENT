"""Muse CLI adapter (T4)."""

from __future__ import annotations

from ._cli import check_binary, run_cli
from .base import Adapter, Reply


class CopilotAdapter(Adapter):
    """Adapter over the ``copilot`` CLI (``copilot -p <prompt>``)."""

    name = "copilot"
    family = "copilot"

    def __init__(self, name: str = "copilot", family: str = "copilot"):
        self.name = name
        self.family = family

    def is_available(self) -> bool:
        # Binary present + best-effort status probe; probe failure is not fatal.
        try:
            return check_binary("copilot", ["copilot", "status"], timeout=5)
        except Exception:
            return False

    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return await run_cli(
            self.name, self.family, ["copilot", "-p", "--", full_prompt], ctx)
