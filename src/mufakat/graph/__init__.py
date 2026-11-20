"""Graph MUFAKAT (T7)."""

from .edges import should_continue_debate, should_revise, track_hash
from .state import RunState

try:
    from .build import SimpleGraph, build_graph
except Exception:  # pragma: no cover
    build_graph = None  # type: ignore
    SimpleGraph = None  # type: ignore

__all__ = [
    "RunState", "should_continue_debate", "should_revise",
    "track_hash", "build_graph", "SimpleGraph",
]
