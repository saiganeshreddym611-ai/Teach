"""Append-only mastery ledger and its projection.

Events are never edited. The current mastery of a node is the *latest* event
for that node; nodes with no event are NOT_MENTIONED. Every event points at
the student turn that produced it, which is the audit trail the pitch needs.
"""
from __future__ import annotations

from .curriculum import Curriculum
from .models import LedgerEvent, MasteryEntry, NodeStatus, NodeVerdict, Phase, Session


def append_verdicts(
    session: Session,
    verdicts: list[NodeVerdict],
    evidence_turn_id: str,
    phase: Phase,
    *,
    focus_node_ids: set[str] | None = None,
) -> list[LedgerEvent]:
    """Write one event per verdict that carries evidence (NOT_MENTIONED is skipped).

    A node already VERIFIED is not downgraded by an incidental later verdict;
    only a verdict on a *focused* node (the teach-back target) may overwrite
    it. That keeps the ledger monotone for the demo; a real product would model
    REVOKED explicitly.
    """
    focus = focus_node_ids or set()
    current = project_status(session)
    written: list[LedgerEvent] = []
    for v in verdicts:
        if v.status == NodeStatus.NOT_MENTIONED:
            continue
        if current.get(v.node_id) == NodeStatus.VERIFIED and v.node_id not in focus:
            continue
        ev = LedgerEvent(
            student_id=session.student_id,
            node_id=v.node_id,
            status=v.status,
            confidence=v.confidence,
            evidence_turn_id=evidence_turn_id,
            phase=phase,
        )
        session.ledger.append(ev)
        written.append(ev)
    return written


def project_status(session: Session) -> dict[str, NodeStatus]:
    status: dict[str, NodeStatus] = {}
    for ev in session.ledger:  # chronological; last write wins
        status[ev.node_id] = ev.status
    return status


def project_confidence(session: Session) -> dict[str, float]:
    conf: dict[str, float] = {}
    for ev in session.ledger:
        conf[ev.node_id] = ev.confidence
    return conf


def mastery_view(session: Session, curriculum: Curriculum) -> list[MasteryEntry]:
    status = project_status(session)
    conf = project_confidence(session)
    return [
        MasteryEntry(
            node_id=n.id,
            title=n.title,
            level=n.level,
            parent=n.parent,
            status=status.get(n.id, NodeStatus.NOT_MENTIONED),
            confidence=conf.get(n.id),
        )
        for n in curriculum.tree.nodes
    ]
