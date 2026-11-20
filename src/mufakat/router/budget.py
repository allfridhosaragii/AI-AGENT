"""Run budget enforcement (T5): cost / request / wall-clock limits."""

from __future__ import annotations

import time


class BudgetExceeded(Exception):
    """Raised when a budget limit is exceeded."""


class Budget:
    """Tracks spend, request count and elapsed wall time for a run."""

    def __init__(self, max_cost_usd: float = 1.0, max_requests: int = 100,
                 max_wall_minutes: float = 60):
        self.max_cost_usd = float(max_cost_usd)
        self.max_requests = int(max_requests)
        self.max_wall_minutes = float(max_wall_minutes)
        self._start = time.monotonic()
        self.cost_usd = 0.0
        self.requests = 0

    def add_cost(self, cost: float) -> None:
        self.cost_usd += float(cost)
        self.check()

    def add_request(self) -> None:
        self.requests += 1
        self.check()

    def elapsed_minutes(self) -> float:
        return (time.monotonic() - self._start) / 60.0

    def check(self) -> None:
        if self.cost_usd > self.max_cost_usd:
            raise BudgetExceeded(
                f"cost ${self.cost_usd:.4f} exceeds max "
                f"${self.max_cost_usd:.4f}")
        if self.requests > self.max_requests:
            raise BudgetExceeded(
                f"requests {self.requests} exceeds max {self.max_requests}")
        if self.elapsed_minutes() > self.max_wall_minutes:
            raise BudgetExceeded(
                f"wall time {self.elapsed_minutes():.2f} min exceeds max "
                f"{self.max_wall_minutes} min")

    def reset(self) -> None:
        self._start = time.monotonic()
        self.cost_usd = 0.0
        self.requests = 0
