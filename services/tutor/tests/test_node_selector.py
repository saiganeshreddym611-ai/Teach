from tutor.models import NodeStatus
from tutor.node_selector import select_next_node


def test_picks_first_level1_when_nothing_known(curriculum):
    assert select_next_node(curriculum, {}, []) == "ind_as_115.step_1"


def test_level1_before_level2_even_if_level2_unverified_earlier_in_file(curriculum):
    status = {"ind_as_115.step_1": NodeStatus.VERIFIED}
    # step_1.criteria (L2) sits before step_2 (L1) in the file, but L1 wins.
    assert select_next_node(curriculum, status, []) == "ind_as_115.step_2"


def test_moves_to_level2_once_all_level1_verified(curriculum):
    status = {n.id: NodeStatus.VERIFIED for n in curriculum.tree.nodes if n.level == 1}
    assert select_next_node(curriculum, status, []) == "ind_as_115.step_1.criteria"


def test_partial_and_gap_are_not_verified(curriculum):
    status = {n.id: NodeStatus.VERIFIED for n in curriculum.tree.nodes if n.level == 1}
    status["ind_as_115.step_1.criteria"] = NodeStatus.PARTIAL
    assert select_next_node(curriculum, status, []) == "ind_as_115.step_1.criteria"
    status["ind_as_115.step_1.criteria"] = NodeStatus.GAP
    assert select_next_node(curriculum, status, []) == "ind_as_115.step_1.criteria"


def test_parked_nodes_skipped_until_everything_else_verified(curriculum):
    status = {}
    assert select_next_node(curriculum, status, ["ind_as_115.step_1"]) == "ind_as_115.step_2"
    status = {n.id: NodeStatus.VERIFIED for n in curriculum.tree.nodes}
    status["ind_as_115.step_1"] = NodeStatus.GAP
    assert select_next_node(curriculum, status, ["ind_as_115.step_1"]) == "ind_as_115.step_1"


def test_none_when_all_verified(curriculum):
    status = {n.id: NodeStatus.VERIFIED for n in curriculum.tree.nodes}
    assert select_next_node(curriculum, status, []) is None
