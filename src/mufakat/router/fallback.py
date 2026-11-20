"""Circuit breaker + fallback chains (T5)."""

from __future__ import annotations

import time

from ..adapters.base import Adapter, AdapterError, Reply

# HTTP-ish failure signals that also trigger a fallback.
_RETRYABLE_TEXT = ("429", "500", "502", "503", "504")


class CircuitBreaker:
    """Per-provider circuit breaker.

    Opens after ``fail_threshold`` consecutive failures and stays open
    for ``open_seconds``; while open, the provider is skipped.
    """

    def __init__(self, fail_threshold: int = 3, open_seconds: float = 600):
        self.fail_threshold = fail_threshold
        self.open_seconds = open_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def record_success(self, provider: str) -> None:
        self._failures.pop(provider, None)
        self._opened_at.pop(provider, None)

    def record_failure(self, provider: str) -> None:
        count = self._failures.get(provider, 0) + 1
        self._failures[provider] = count
        if count >= self.fail_threshold:
            self._opened_at[provider] = time.monotonic()

    def is_open(self, provider: str) -> bool:
        opened_at = self._opened_at.get(provider)
        if opened_at is None:
            return False
        if time.monotonic() - opened_at >= self.open_seconds:
            # Half-open: allow a probe; failures will re-open it.
            self._opened_at.pop(provider, None)
            self._failures.pop(provider, None)
            return False
        return True


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, AdapterError):
        return True  # AdapterError covers 429/5xx/network/timeout.
    return any(code in str(exc) for code in _RETRYABLE_TEXT)


class FallbackChain:
    """Try providers for a role in order, skipping open circuits.

    ``chains``: ``{role: [provider_name, ...]}``.
    ``adapters``: ``{provider_name: Adapter}``.
    """

    def __init__(self, chains: dict[str, list[str]],
                 adapters: dict[str, Adapter],
                 breaker: CircuitBreaker | None = None):
        self.chains = chains
        self.adapters = adapters
        self.breaker = breaker or CircuitBreaker()

    async def ask_with_fallback(self, role: str, prompt: str,
                                system: str = "",
                                ctx: dict | None = None) -> Reply:
        chain = self.chains.get(role)
        if not chain:
            raise AdapterError(f"no fallback chain configured for role {role!r}")
        errors: list[str] = []
        for provider in chain:
            if self.breaker.is_open(provider):
                errors.append(f"{provider}: circuit open, skipped")
                continue
            adapter = self.adapters.get(provider)
            if adapter is None:
                errors.append(f"{provider}: adapter not registered")
                continue
            try:
                reply = await adapter.ask(prompt, system=system, ctx=ctx)
            except Exception as exc:  # noqa: BLE001 - any failure falls back
                self.breaker.record_failure(provider)
                errors.append(f"{provider}: {exc}")
                if not _is_retryable(exc):
                    # Non-retryable errors still fall through to the next
                    # provider; only the final raise differs in message.
                    continue
                continue
            self.breaker.record_success(provider)
            return reply
        raise AdapterError(
            f"all providers failed for role {role!r}: " + "; ".join(errors))
