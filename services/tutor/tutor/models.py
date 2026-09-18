"""Pydantic models shared across the service.

Naming follows the pitch: a *knowledge tree* of *nodes* graded into a
*mastery ledger* of append-only *events*.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Curriculum
# --------------------------------------------------------------------------- #
class Node(BaseModel):
    id: str
    level: Literal[1, 2, 3]
    parent: str | None
    title: str
    rubric: list[str]
    misconceptions: list[str] = []
    canonical_explanation: str
    example: str = ""
    source_refs: list[str] = []


class Tree(BaseModel):
    topic_id: str
    subject: str
    standard: str
    opening_prompt: str
    nodes: list[Node]


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #
class NodeStatus(str, Enum):
    NOT_MENTIONED = "NOT_MENTIONED"  # no evidence either way
    GAP = "GAP"                      # mentioned but wrong, or explicitly missing
    PARTIAL = "PARTIAL"              # some rubric items evidenced, not all
    VERIFIED = "VERIFIED"            # every rubric item evidenced accurately


class NodeVerdict(BaseModel):
    node_id: str
    status: NodeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(
        description="Short quote or paraphrase from the student's words that supports the verdict; empty if NOT_MENTIONED."
    )


class GraderResult(BaseModel):
    """Structured output of the grader call. Deepest missing node is NOT here on
    purpose - the node selector (pure code) decides that."""
    verdicts: list[NodeVerdict]
    summary: str = Field(description="One sentence on the student's overall level, for the tutor.")


# --------------------------------------------------------------------------- #
# Session / ledger
# --------------------------------------------------------------------------- #
class Phase(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    INSTRUCT = "INSTRUCT"
    TEACH_BACK = "TEACH_BACK"
    COMPLETE = "COMPLETE"


class Turn(BaseModel):
    id: str = Field(default_factory=_uid)
    role: Literal["student", "tutor"]
    text: str
    phase: Phase
    ts: datetime = Field(default_factory=_now)


class LedgerEvent(BaseModel):
    id: str = Field(default_factory=_uid)
    student_id: str
    node_id: str
    status: NodeStatus
    confidence: float
    evidence_turn_id: str
    phase: Phase
    ts: datetime = Field(default_factory=_now)


class Session(BaseModel):
    id: str = Field(default_factory=_uid)
    student_id: str
    topic_id: str
    phase: Phase = Phase.DIAGNOSTIC
    target_node: str | None = None
    instruct_turns_on_node: int = 0
    teach_back_attempts: dict[str, int] = {}
    parked_nodes: list[str] = []          # gave up after max attempts; revisit later
    turns: list[Turn] = []
    ledger: list[LedgerEvent] = []
    student_level_summary: str = ""
    created_at: datetime = Field(default_factory=_now)


# --------------------------------------------------------------------------- #
# API shapes
# --------------------------------------------------------------------------- #
class CreateSessionRequest(BaseModel):
    student_id: str = "demo_student"
    topic_id: str = "ind_as_115"


class CreateSessionResponse(BaseModel):
    session_id: str
    phase: Phase
    opening_prompt: str


class TurnRequest(BaseModel):
    transcript: str = Field(min_length=1)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)
    voice: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


class MasteryEntry(BaseModel):
    node_id: str
    title: str
    level: int
    parent: str | None
    status: NodeStatus
    confidence: float | None = None


class SessionView(BaseModel):
    session_id: str
    student_id: str
    topic_id: str
    phase: Phase
    target_node: str | None
    student_level_summary: str
    mastery: list[MasteryEntry]
    turns: list[Turn]
    ledger: list[LedgerEvent]
