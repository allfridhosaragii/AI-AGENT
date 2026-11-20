"""Node graph MUFAKAT (T7)."""

from .audit import node as audit
from .code import node as code
from .critique import node as critique
from .debate import node as debate
from .meeting import node as meeting
from .research import node as research
from .review import node as review
from .revise import node as revise
from .spec import node as spec
from .test import node as test

NODES = {
    "research": research,
    "debate": debate,
    "critique": critique,
    "meeting": meeting,
    "spec": spec,
    "code": code,
    "review": review,
    "audit": audit,
    "test": test,
    "revise": revise,
}

__all__ = ["NODES", "research", "debate", "critique", "meeting", "spec",
           "code", "review", "audit", "test", "revise"]
