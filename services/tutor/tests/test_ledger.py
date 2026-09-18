from tutor.ledger import append_verdicts, mastery_view, project_status
from tutor.models import NodeStatus, Phase
from tests.conftest import verdict


def test_events_are_append_only_and_last_wins(session):
    append_verdicts(session, [verdict("ind_as_115.step_1", "PARTIAL")], "t1", Phase.DIAGNOSTIC)
    append_verdicts(session, [verdict("ind_as_115.step_1", "VERIFIED")], "t2", Phase.TEACH_BACK, focus_node_ids={"ind_as_115.step_1"})
    assert len(session.ledger) == 2
    assert project_status(session)["ind_as_115.step_1"] == NodeStatus.VERIFIED
    assert [e.evidence_turn_id for e in session.ledger] == ["t1", "t2"]


def test_not_mentioned_is_never_written(session):
    written = append_verdicts(session, [verdict("ind_as_115.step_1", "NOT_MENTIONED")], "t1", Phase.DIAGNOSTIC)
    assert written == [] and session.ledger == []


def test_verified_is_not_downgraded_by_incidental_verdict(session):
    append_verdicts(session, [verdict("ind_as_115.step_1", "VERIFIED")], "t1", Phase.DIAGNOSTIC)
    written = append_verdicts(session, [verdict("ind_as_115.step_1", "PARTIAL")], "t2", Phase.TEACH_BACK, focus_node_ids={"other"})
    assert written == []
    assert project_status(session)["ind_as_115.step_1"] == NodeStatus.VERIFIED


def test_focused_verdict_may_overwrite_verified(session):
    append_verdicts(session, [verdict("ind_as_115.step_1", "VERIFIED")], "t1", Phase.DIAGNOSTIC)
    append_verdicts(session, [verdict("ind_as_115.step_1", "GAP")], "t2", Phase.TEACH_BACK, focus_node_ids={"ind_as_115.step_1"})
    assert project_status(session)["ind_as_115.step_1"] == NodeStatus.GAP


def test_mastery_view_covers_every_node(session, curriculum):
    append_verdicts(session, [verdict("ind_as_115.step_4", "VERIFIED", conf=0.8)], "t1", Phase.DIAGNOSTIC)
    view = mastery_view(session, curriculum)
    assert len(view) == len(curriculum.tree.nodes)
    by_id = {m.node_id: m for m in view}
    assert by_id["ind_as_115.step_4"].status == NodeStatus.VERIFIED
    assert by_id["ind_as_115.step_4"].confidence == 0.8
    assert by_id["ind_as_115.step_5"].status == NodeStatus.NOT_MENTIONED
    assert by_id["ind_as_115.step_5"].confidence is None
