"""Proposal anonymization for blind consensus review (T6).

Proposals are shuffled and relabelled (A, B, C, ...) so reviewers
cannot tell which agent wrote which proposal.  The mapping
label -> agent_id is kept out-of-band and used by ``deanonymize``.
"""

from __future__ import annotations

import random
import string

try:  # Optional: protocol.py is owned by another subagent.
    from .protocol import MufakatMessage  # noqa: F401
except ImportError:  # pragma: no cover
    MufakatMessage = None  # type: ignore


def _label(index: int) -> str:
    """Excel-style label: 0->A, 25->Z, 26->AA, ..."""
    name = ""
    n = index
    while True:
        name = string.ascii_uppercase[n % 26] + name
        n = n // 26 - 1
        if n < 0:
            return name


class AnonymizedProposals(list):
    """A list of anonymized proposal dicts carrying its label mapping.

    Behaves exactly like ``list[dict]``; the ``mapping`` attribute
    (``label -> agent_id``) is the out-of-band lookup for
    :func:`deanonymize`.
    """

    def __init__(self, items: list[dict], mapping: dict[str, str]):
        super().__init__(items)
        self.mapping = mapping


def anonymize(proposals: list[dict], seed: int | None = None
              ) -> AnonymizedProposals:
    """Shuffle *proposals* and relabel them anonymously.

    Each proposal dict must carry ``agent_id`` (and any other fields,
    e.g. ``text``).  Returns a list of dicts with ``label`` and the
    original content minus ``agent_id``; the label->agent_id mapping
    is available as ``result.mapping`` for :func:`deanonymize`.
    """
    rng = random.Random(seed)
    shuffled = list(proposals)
    rng.shuffle(shuffled)
    anonymized: list[dict] = []
    mapping: dict[str, str] = {}
    for i, proposal in enumerate(shuffled):
        label = _label(i)
        agent_id = proposal.get("agent_id", "")
        mapping[label] = agent_id
        clean = {k: v for k, v in proposal.items() if k != "agent_id"}
        clean["label"] = label
        anonymized.append(clean)
    return AnonymizedProposals(anonymized, mapping)


def deanonymize(mapping: dict[str, str], label: str) -> str | None:
    """Return the original ``agent_id`` for *label*, or None if unknown."""
    return mapping.get(label)
