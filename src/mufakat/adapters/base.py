"""Base adapter contract for MUFAKAT multi-AI modules.

Every adapter (HTTP API or CLI) must subclass :class:`Adapter` and
implement ``ask`` (async) and ``is_available`` (sync, never raises).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


class AdapterError(Exception):
    """Raised when an adapter fails to produce a reply (network, CLI,
    provider 429/5xx after retries, malformed output, ...)."""


@dataclass
class Reply:
    """One reply from a provider adapter."""

    text: str
    usage: dict = field(default_factory=lambda: {
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
    })
    provider: str = ""
    family: str = ""
    raw: str = ""


class Adapter(abc.ABC):
    """Common interface for all MUFAKAT adapters."""

    name: str = ""
    family: str = ""

    @abc.abstractmethod
    async def ask(self, prompt: str, system: str = "",
                  ctx: dict | None = None) -> Reply:
        """Send *prompt* (with optional *system* message) and return a Reply.

        ``ctx`` may carry e.g. ``cwd`` and ``timeout`` for CLI adapters.
        Raises AdapterError on failure.
        """

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Sync availability check (binary present / login ok).

        Short timeout, must never raise.
        """
