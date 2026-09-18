"""OllamaGrader plumbing with a fake client - no server, no network."""
import json
from types import SimpleNamespace

import pytest

from tutor.grader import OLLAMA_OUTPUT_CONTRACT, OllamaGrader, _inline_schema
from tutor.models import GraderResult, NodeStatus


GOOD = json.dumps({
    "verdicts": [
        {"node_id": "ind_as_115.step_4.ssp", "status": "GAP", "confidence": 0.9, "evidence": "based on cost"},
        {"node_id": "not.in.tree", "status": "VERIFIED", "confidence": 0.9, "evidence": "x"},
    ],
    "summary": "Allocates on cost, not SSP.",
})
# The shape the model produced before the output contract was added.
BAD = json.dumps({"ind_as_115.step_4.ssp": {"verdict": "GAP", "evidence": "based on cost"}})


class FakeOllama:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    async def chat(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(
            message=SimpleNamespace(content=self.contents.pop(0)),
            model=kw["model"], prompt_eval_count=100, eval_count=50, total_duration=2_000_000_000,
        )


def test_inline_schema_has_no_refs_and_forbids_extra_keys():
    s = _inline_schema(GraderResult.model_json_schema())
    dumped = json.dumps(s)
    assert "$ref" not in dumped and "$defs" not in dumped
    assert s["additionalProperties"] is False
    item = s["properties"]["verdicts"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["properties"]["status"]["enum"]) == {e.value for e in NodeStatus}


async def test_happy_path_sends_schema_and_contract(curriculum):
    fake = FakeOllama([GOOD])
    g = OllamaGrader(client=fake, model="fake-model")
    res = await g.grade(curriculum, "we allocate on cost", focus_node_id="ind_as_115.step_4.ssp",
                        prior_context="Tutor asked: explain SSP", session_id="t")
    assert len(fake.calls) == 1
    kw = fake.calls[0]
    assert kw["model"] == "fake-model"
    assert kw["format"] == g.schema
    assert kw["options"]["temperature"] == 0
    assert OLLAMA_OUTPUT_CONTRACT.strip() in kw["messages"][0]["content"]
    assert "<knowledge_tree" in kw["messages"][0]["content"]
    assert "TEACH-BACK" in kw["messages"][1]["content"]
    # off-tree id dropped, in-tree verdict kept
    assert [v.node_id for v in res.verdicts] == ["ind_as_115.step_4.ssp"]
    assert res.verdicts[0].status == NodeStatus.GAP


async def test_wrong_shape_triggers_one_corrective_retry(curriculum):
    fake = FakeOllama([BAD, GOOD])
    g = OllamaGrader(client=fake, model="fake-model")
    res = await g.grade(curriculum, "x", focus_node_id=None, prior_context="", session_id="t")
    assert len(fake.calls) == 2
    retry_msgs = fake.calls[1]["messages"]
    assert retry_msgs[-2] == {"role": "assistant", "content": BAD}
    assert "verdicts" in retry_msgs[-1]["content"]
    assert res.summary == "Allocates on cost, not SSP."


async def test_wrong_shape_twice_raises(curriculum):
    fake = FakeOllama([BAD, BAD])
    g = OllamaGrader(client=fake, model="fake-model")
    with pytest.raises(RuntimeError, match="invalid JSON twice"):
        await g.grade(curriculum, "x", focus_node_id=None, prior_context="", session_id="t")
