"""The learning loop as a state machine.

    DIAGNOSTIC --(grade)--> pick deepest unverified node --> INSTRUCT
    INSTRUCT   --(tutor turn; sentinel => teach-back requested)--> TEACH_BACK
    TEACH_BACK --(grade target)--> VERIFIED: ledger event, next node -> INSTRUCT
                                   not yet : retry (max N) then park -> INSTRUCT
    nothing left --> COMPLETE

Code owns every transition. The LLMs are called at fixed points: the grader
after DIAGNOSTIC and TEACH_BACK utterances, the tutor on every turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from .config import settings
from .curriculum import Curriculum
from .grader import Grader
from .ledger import append_verdicts, project_status
from .models import GraderResult, LedgerEvent, NodeStatus, Phase, Session, Turn
from .node_selector import select_next_node
from .prompts import TEACH_BACK_SENTINEL
from .tutor_voice import TutorVoice


@dataclass
class TurnEvent:
    kind: str  # "grade" | "text" | "done" | "error"
    payload: dict[str, Any] = field(default_factory=dict)


class SentinelFilter:
    """Streams text through while holding back anything that could be the start
    of the sentinel, so a partial `<<TEACH_` never reaches the speaker."""

    def __init__(self, sentinel: str = TEACH_BACK_SENTINEL):
        self.sentinel = sentinel
        self.buf = ""
        self.found = False

    def feed(self, delta: str) -> str:
        self.buf += delta
        if self.sentinel in self.buf:
            self.found = True
            self.buf = self.buf.replace(self.sentinel, "")
        cut = len(self.buf)
        start = max(0, len(self.buf) - len(self.sentinel) + 1)
        for i in range(start, len(self.buf)):
            if self.buf[i] == "<" and self.sentinel.startswith(self.buf[i:]):
                cut = i
                break
        out, self.buf = self.buf[:cut], self.buf[cut:]
        return out

    def flush(self) -> str:
        if self.sentinel in self.buf:
            self.found = True
            self.buf = self.buf.replace(self.sentinel, "")
        out, self.buf = self.buf, ""
        return out


# --------------------------------------------------------------------------- #
# Directives - the per-turn operator instruction sent as a system message.
# --------------------------------------------------------------------------- #
def _node_line(curriculum: Curriculum, node_id: str) -> str:
    n = curriculum.node(node_id)
    return f'Target node: `{n.id}` - "{n.title}" (level {n.level}).'


def _verified_titles(session: Session, curriculum: Curriculum) -> str:
    status = project_status(session)
    titles = [curriculum.node(nid).title for nid, s in status.items() if s == NodeStatus.VERIFIED]
    return "; ".join(titles) if titles else "nothing yet"


def _introduce(curriculum: Curriculum, session: Session, node_id: str, preface: str) -> str:
    return (
        "PHASE=INSTRUCT ACTION=INTRODUCE_NODE\n"
        f"{preface}"
        f"{_node_line(curriculum, node_id)}\n"
        f"Student level: {session.student_level_summary or 'unknown'}\n"
        f"Verified so far: {_verified_titles(session, curriculum)}\n"
        "Do: teach the target node using its canonical_explanation and example, pitched to the student's level. "
        "Under 120 words. End with one check question. Do NOT request a teach-back on this turn."
    )


def _continue(curriculum: Curriculum, session: Session, force_teach_back: bool) -> str:
    turn = session.instruct_turns_on_node
    if force_teach_back:
        return (
            "PHASE=INSTRUCT ACTION=REQUEST_TEACH_BACK\n"
            f"{_node_line(curriculum, session.target_node)}\n"
            f"This is instruct turn {turn} of {settings.max_instruct_turns_per_node}; time is up for explanation.\n"
            "Do: respond in one sentence to what the student just said, then ask them to explain the target node "
            f"back to you in their own words with an example, then append the silent marker {TEACH_BACK_SENTINEL}."
        )
    return (
        "PHASE=INSTRUCT ACTION=CONTINUE\n"
        f"{_node_line(curriculum, session.target_node)}\n"
        f"This is instruct turn {turn} of {settings.max_instruct_turns_per_node}.\n"
        "Do: respond to what the student just said about this node - answer their question or correct the misconception. "
        "If they clearly understand it now, ask them to explain it back in their own words with an example and "
        f"append the silent marker {TEACH_BACK_SENTINEL}. Otherwise keep teaching and end with one check question."
    )


def _teach_back_failed(curriculum: Curriculum, session: Session, result: GraderResult, attempt: int) -> str:
    node = curriculum.node(session.target_node)
    verdict = next((v for v in result.verdicts if v.node_id == node.id), None)
    vtext = f"{verdict.status.value} (evidence: \"{verdict.evidence}\")" if verdict else "no evidence"
    rubric = " | ".join(node.rubric)
    return (
        "PHASE=INSTRUCT ACTION=TEACH_BACK_FAILED\n"
        f"{_node_line(curriculum, node.id)}\n"
        f"Attempt {attempt} of {settings.max_teach_back_attempts}. Grader verdict: {vtext}.\n"
        f"Rubric the student must cover: {rubric}\n"
        "Do: say specifically which rubric point was missing or wrong, re-explain only that part in under 80 words, "
        f"then ask them to explain the whole concept back once more, then append the silent marker {TEACH_BACK_SENTINEL}."
    )


def _complete(curriculum: Curriculum, session: Session) -> str:
    parked = ", ".join(curriculum.node(n).title for n in session.parked_nodes) or "none"
    return (
        "PHASE=COMPLETE\n"
        f"Verified: {_verified_titles(session, curriculum)}\n"
        f"Parked for later: {parked}\n"
        "Do: summarise in two or three sentences what the student has mastered, mention anything parked, "
        "encourage them, and end by asking what they want to study next."
    )


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
def _delta_payload(events: list[LedgerEvent]) -> list[dict]:
    return [e.model_dump(mode="json") for e in events]


async def run_turn(
    session: Session,
    transcript: str,
    curriculum: Curriculum,
    grader: Grader,
    tutor: TutorVoice,
) -> AsyncIterator[TurnEvent]:
    student_turn = Turn(role="student", text=transcript, phase=session.phase)
    session.turns.append(student_turn)

    ledger_delta: list[LedgerEvent] = []
    directive: str

    if session.phase == Phase.DIAGNOSTIC:
        result = await grader.grade(
            curriculum, transcript, focus_node_id=None, prior_context="", session_id=session.id
        )
        ledger_delta = append_verdicts(session, result.verdicts, student_turn.id, Phase.DIAGNOSTIC)
        session.student_level_summary = result.summary
        yield TurnEvent("grade", {"verdicts": [v.model_dump() for v in result.verdicts], "summary": result.summary})
        directive = _advance_to_next_node(curriculum, session, preface="")

    elif session.phase == Phase.INSTRUCT:
        session.instruct_turns_on_node += 1
        force = session.instruct_turns_on_node >= settings.max_instruct_turns_per_node
        directive = _continue(curriculum, session, force_teach_back=force)

    elif session.phase == Phase.TEACH_BACK:
        target = session.target_node
        last_tutor = next((t.text for t in reversed(session.turns) if t.role == "tutor"), "")
        result = await grader.grade(
            curriculum, transcript, focus_node_id=target, prior_context=f"Tutor asked: {last_tutor}", session_id=session.id
        )
        ledger_delta = append_verdicts(
            session, result.verdicts, student_turn.id, Phase.TEACH_BACK, focus_node_ids={target}
        )
        yield TurnEvent("grade", {"verdicts": [v.model_dump() for v in result.verdicts], "summary": result.summary})
        verdict = next((v for v in result.verdicts if v.node_id == target), None)
        if verdict and verdict.status == NodeStatus.VERIFIED:
            title = curriculum.node(target).title
            directive = _advance_to_next_node(
                curriculum, session, preface=f'Previous node "{title}" is now VERIFIED. Congratulate in one sentence first.\n'
            )
        else:
            attempts = session.teach_back_attempts.get(target, 0) + 1
            session.teach_back_attempts[target] = attempts
            if attempts >= settings.max_teach_back_attempts:
                session.parked_nodes.append(target)
                title = curriculum.node(target).title
                directive = _advance_to_next_node(
                    curriculum,
                    session,
                    preface=f'Previous node "{title}" is parked after {attempts} attempts. Say you will come back to it later - one sentence, no lecture.\n',
                )
            else:
                session.phase = Phase.INSTRUCT
                session.instruct_turns_on_node = 0
                directive = _teach_back_failed(curriculum, session, result, attempts)

    else:  # COMPLETE - keep chatting, no grading
        directive = _complete(curriculum, session)

    # ---- tutor turn (streamed) ------------------------------------------- #
    filt = SentinelFilter()
    spoken_parts: list[str] = []
    async for delta in tutor.stream(curriculum, session, directive):
        out = filt.feed(delta)
        if out:
            spoken_parts.append(out)
            yield TurnEvent("text", {"delta": out})
    tail = filt.flush()
    if tail:
        spoken_parts.append(tail)
        yield TurnEvent("text", {"delta": tail})

    spoken = "".join(spoken_parts).strip()
    tutor_turn = Turn(role="tutor", text=spoken, phase=session.phase)
    session.turns.append(tutor_turn)

    if filt.found and session.phase == Phase.INSTRUCT:
        session.phase = Phase.TEACH_BACK

    yield TurnEvent(
        "done",
        {
            "phase": session.phase.value,
            "target_node": session.target_node,
            "tutor_turn_id": tutor_turn.id,
            "student_turn_id": student_turn.id,
            "ledger_delta": _delta_payload(ledger_delta),
        },
    )


def _advance_to_next_node(curriculum: Curriculum, session: Session, preface: str) -> str:
    nxt = select_next_node(curriculum, project_status(session), session.parked_nodes)
    if nxt is None:
        session.phase = Phase.COMPLETE
        session.target_node = None
        return _complete(curriculum, session)
    session.target_node = nxt
    session.instruct_turns_on_node = 0
    session.phase = Phase.INSTRUCT
    return _introduce(curriculum, session, nxt, preface)
