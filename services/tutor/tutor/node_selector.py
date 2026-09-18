"""Pure-code implementation of "Identify Deepest Missing Node".

Walk Level 1 -> 2 -> 3 in document order and return the first node that is not
VERIFIED and not parked. Parked nodes (max teach-back attempts exhausted) are
only revisited once everything else is verified.
"""
from __future__ import annotations

from .curriculum import Curriculum
from .models import NodeStatus


def select_next_node(
    curriculum: Curriculum,
    status: dict[str, NodeStatus],
    parked: list[str],
    *,
    max_level: int = 3,
) -> str | None:
    candidates = [n for n in curriculum.tree.nodes if n.level <= max_level]
    candidates.sort(key=lambda n: (n.level, curriculum.order[n.id]))
    for n in candidates:
        if n.id in parked:
            continue
        if status.get(n.id, NodeStatus.NOT_MENTIONED) != NodeStatus.VERIFIED:
            return n.id
    # Everything unparked is verified - give parked nodes another go, in order.
    for n in candidates:
        if n.id in parked and status.get(n.id) != NodeStatus.VERIFIED:
            return n.id
    return None
