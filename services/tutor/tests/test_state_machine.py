"""Drive run_turn with scripted grader/tutor and assert the transitions in
the plan's §4.3 table. No network."""
import pytest

from tutor.config import settings
from tutor.ledger import project_status
from tutor.models import NodeStatus, Phase
from tutor.state_machine import run_turn
from tests.conftest import SENT, ScriptedGrader, ScriptedTutor, result, verdict


async def drive(session, curriculum, grader, tutor, transcript):
    events = []
    async for ev in run_turn(session, transcript, curriculum, grader, tutor):
        events.append(ev)
    return events


def kinds(events):
    return [e.kind for e in events]


def spoken(events):
    return "".join(e.payload["delta"] for e in events if e.kind == "text")


# --------------------------------------------------------------------------- #
# DIAGNOSTIC -> INSTRUCT
# --------------------------------------------------------------------------- #
async def test_diagnostic_grades_writes_ledger_and_targets_deepest_missing(session, curriculum):
    grader = ScriptedGrader([
        result(
            verdict("ind_as_115.step_1", "VERIFIED"),
            verdict("ind_as_115.step_2", "VERIFIED"),
            verdict("ind_as_115.step_3", "PARTIAL"),
            summary="Knows steps 1-2, shaky on 3.",
        )
    ])
    tutor = ScriptedTutor(["Nice start. Let's look at transaction price. What is it?"])

    events = await drive(session, curriculum, grader, tutor, "step one identify contract step two obligations step three price maybe")

    assert kinds(events) == ["grade", "text", "text", "text", "text", "text", "text", "text", "text", "done"][: len(events)]
    assert events[0].kind == "grade" and events[-1].kind == "done"
    assert grader.calls[0]["focus"] is None
    # Ledger has the three evidence-bearing verdicts, each pointing at the student turn.
    student_turn_id = events[-1].payload["student_turn_id"]
    assert [e.evidence_turn_id for e in session.ledger] == [student_turn_id] * 3
    assert project_status(session)["ind_as_115.step_3"] == NodeStatus.PARTIAL
    # Node selector (code) picked step_3 - first non-VERIFIED L1 - not the LLM.
    assert session.phase == Phase.INSTRUCT
    assert session.target_node == "ind_as_115.step_3"
    assert "ACTION=INTRODUCE_NODE" in tutor.directives[0]
    assert "ind_as_115.step_3" in tutor.directives[0]
    assert session.student_level_summary == "Knows steps 1-2, shaky on 3."
    assert events[-1].payload["phase"] == "INSTRUCT"
    assert len(events[-1].payload["ledger_delta"]) == 3
    # Transcript recorded: student turn + tutor turn.
    assert [t.role for t in session.turns] == ["student", "tutor"]
    assert session.turns[-1].text == "Nice start. Let's look at transaction price. What is it?"


# --------------------------------------------------------------------------- #
# INSTRUCT: no grading; sentinel flips to TEACH_BACK; forced after N turns
# --------------------------------------------------------------------------- #
async def test_instruct_turn_does_not_grade_and_sentinel_moves_to_teach_back(session, curriculum):
    session.phase = Phase.INSTRUCT
    session.target_node = "ind_as_115.step_4"
    grader = ScriptedGrader([])  # any call would IndexError
    tutor = ScriptedTutor(["Right. Now explain allocation back to me with an example. " + SENT])

    events = await drive(session, curriculum, grader, tutor, "so it's based on standalone prices?")

    assert "grade" not in kinds(events)
    assert grader.calls == []
    assert "ACTION=CONTINUE" in tutor.directives[0]
    assert SENT not in spoken(events)
    assert session.turns[-1].text == "Right. Now explain allocation back to me with an example."
    assert session.phase == Phase.TEACH_BACK
    assert session.instruct_turns_on_node == 1


async def test_instruct_without_sentinel_stays_in_instruct(session, curriculum):
    session.phase = Phase.INSTRUCT
    session.target_node = "ind_as_115.step_4"
    tutor = ScriptedTutor(["Not quite. SSP means... Does that help?"])

    await drive(session, curriculum, ScriptedGrader([]), tutor, "is it cost based?")

    assert session.phase == Phase.INSTRUCT


async def test_teach_back_is_forced_after_max_instruct_turns(session, curriculum, monkeypatch):
    monkeypatch.setattr(settings, "max_instruct_turns_per_node", 2)
    session.phase = Phase.INSTRUCT
    session.target_node = "ind_as_115.step_4"
    tutor = ScriptedTutor(["Keep going. Question?", "Ok, explain it back. " + SENT])

    await drive(session, curriculum, ScriptedGrader([]), tutor, "hmm")
    assert "ACTION=CONTINUE" in tutor.directives[0]
    assert session.phase == Phase.INSTRUCT

    await drive(session, curriculum, ScriptedGrader([]), tutor, "ok")
    assert "ACTION=REQUEST_TEACH_BACK" in tutor.directives[1]
    assert session.phase == Phase.TEACH_BACK


# --------------------------------------------------------------------------- #
# TEACH_BACK: verified -> ledger + next node; failed -> retry; twice -> park
# --------------------------------------------------------------------------- #
async def test_teach_back_verified_writes_ledger_and_advances(session, curriculum):
    session.phase = Phase.TEACH_BACK
    session.target_node = "ind_as_115.step_1"
    session.turns.append(__import__("tutor.models", fromlist=["Turn"]).Turn(role="tutor", text="Explain step 1 back.", phase=Phase.INSTRUCT))
    grader = ScriptedGrader([result(verdict("ind_as_115.step_1", "VERIFIED", evidence="a contract is an enforceable agreement"))])
    tutor = ScriptedTutor(["Exactly right. Next, performance obligations. What is one?"])

    events = await drive(session, curriculum, grader, tutor, "a contract is an agreement with enforceable rights, oral or written")

    assert grader.calls[0]["focus"] == "ind_as_115.step_1"
    assert grader.calls[0]["prior"] == "Tutor asked: Explain step 1 back."
    assert project_status(session)["ind_as_115.step_1"] == NodeStatus.VERIFIED
    assert session.ledger[-1].phase == Phase.TEACH_BACK
    assert session.phase == Phase.INSTRUCT
    assert session.target_node == "ind_as_115.step_2"
    assert "is now VERIFIED" in tutor.directives[0]
    assert "ACTION=INTRODUCE_NODE" in tutor.directives[0]


async def test_teach_back_failed_retries_then_parks(session, curriculum, monkeypatch):
    monkeypatch.setattr(settings, "max_teach_back_attempts", 2)
    session.phase = Phase.TEACH_BACK
    session.target_node = "ind_as_115.step_1"
    grader = ScriptedGrader([
        result(verdict("ind_as_115.step_1", "PARTIAL", evidence="it's the first step")),
        result(verdict("ind_as_115.step_1", "GAP", evidence="must be written")),
    ])
    tutor = ScriptedTutor([
        "Close. A contract can be oral too. Try again. " + SENT,
        "We'll come back to that. Next, performance obligations. What is one?",
    ])

    # Attempt 1: fail -> back to INSTRUCT on same node, tutor asks again -> TEACH_BACK
    await drive(session, curriculum, grader, tutor, "it's the first step")
    assert "ACTION=TEACH_BACK_FAILED" in tutor.directives[0]
    assert "Attempt 1 of 2" in tutor.directives[0]
    assert session.target_node == "ind_as_115.step_1"
    assert session.phase == Phase.TEACH_BACK  # sentinel re-requested teach-back
    assert session.teach_back_attempts["ind_as_115.step_1"] == 1

    # Attempt 2: fail -> park, move on
    await drive(session, curriculum, grader, tutor, "a contract must be written")
    assert session.parked_nodes == ["ind_as_115.step_1"]
    assert "is parked after 2 attempts" in tutor.directives[1]
    assert session.phase == Phase.INSTRUCT
    assert session.target_node == "ind_as_115.step_2"
    assert project_status(session)["ind_as_115.step_1"] == NodeStatus.GAP


# --------------------------------------------------------------------------- #
# COMPLETE
# --------------------------------------------------------------------------- #
async def test_all_verified_goes_complete(session, curriculum):
    session.phase = Phase.DIAGNOSTIC
    grader = ScriptedGrader([result(*[verdict(n.id, "VERIFIED") for n in curriculum.tree.nodes], summary="Expert.")])
    tutor = ScriptedTutor(["You've mastered all of it. What next?"])

    events = await drive(session, curriculum, grader, tutor, "(a perfect monologue)")

    assert session.phase == Phase.COMPLETE
    assert session.target_node is None
    assert "PHASE=COMPLETE" in tutor.directives[0]
    assert events[-1].payload["phase"] == "COMPLETE"


async def test_complete_phase_keeps_chatting_without_grading(session, curriculum):
    session.phase = Phase.COMPLETE
    tutor = ScriptedTutor(["Ind AS 116 next then. Ready?"])
    events = await drive(session, curriculum, ScriptedGrader([]), tutor, "what next?")
    assert "grade" not in kinds(events)
    assert session.phase == Phase.COMPLETE
