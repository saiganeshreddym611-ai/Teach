"""End-to-end through FastAPI with the mock LLMs: create session -> diagnostic
-> instruct -> teach-back -> ledger updated. Parses the SSE stream by hand."""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from tutor import main
from tutor.grader import MockGrader
from tutor.tutor_voice import MockTutor


@pytest.fixture(autouse=True)
def use_mocks(monkeypatch):
    monkeypatch.setattr(main, "get_grader", lambda: MockGrader())
    monkeypatch.setattr(main, "get_tutor", lambda: MockTutor())


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        kind, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                kind = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if kind:
            events.append((kind, data))
    return events


async def post_turn(client, sid, transcript):
    r = await client.post(f"/session/{sid}/turn", json={"transcript": transcript})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return parse_sse(r.text)


async def test_full_loop_over_http():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
        assert r.json()["ok"] is True

        r = await client.post("/session", json={"student_id": "s1", "topic_id": "ind_as_115"})
        assert r.status_code == 200
        sid = r.json()["session_id"]
        assert r.json()["phase"] == "DIAGNOSTIC"
        assert "Ind AS 115" in r.json()["opening_prompt"]

        # Diagnostic: student names step 1 in enough detail for the keyword mock.
        events = await post_turn(
            client, sid,
            "the first step of the five step model is identifying the contract with the customer, "
            "an agreement creating enforceable rights and obligations, written oral or implied",
        )
        kinds = [k for k, _ in events]
        assert kinds[0] == "grade" and kinds[-1] == "done"
        assert "text" in kinds
        done = events[-1][1]
        assert done["phase"] == "INSTRUCT"
        assert done["target_node"] is not None
        target = done["target_node"]

        view = (await client.get(f"/session/{sid}")).json()
        assert view["phase"] == "INSTRUCT"
        assert len(view["mastery"]) == 42
        assert len(view["ledger"]) >= 1
        assert view["ledger"][0]["evidence_turn_id"] == done["student_turn_id"]

        # Instruct turn: mock tutor requests teach-back (sentinel) -> TEACH_BACK, no grade event.
        events = await post_turn(client, sid, "ok I think I follow")
        assert "grade" not in [k for k, _ in events]
        assert events[-1][1]["phase"] == "TEACH_BACK"
        spoken = "".join(d["delta"] for k, d in events if k == "text")
        assert "<<" not in spoken

        # Teach-back: echo the node's own rubric words so the keyword mock verifies it.
        from tutor.curriculum import load_curriculum
        node = load_curriculum("ind_as_115").node(target)
        events = await post_turn(client, sid, node.title + " " + " ".join(node.rubric))
        grade = next(d for k, d in events if k == "grade")
        assert any(v["node_id"] == target and v["status"] == "VERIFIED" for v in grade["verdicts"])
        done = events[-1][1]
        assert done["target_node"] != target  # advanced to the next node
        assert any(e["node_id"] == target and e["status"] == "VERIFIED" for e in done["ledger_delta"])

        view = (await client.get(f"/session/{sid}")).json()
        assert next(m for m in view["mastery"] if m["node_id"] == target)["status"] == "VERIFIED"


async def test_unknown_session_404():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/session/nope")).status_code == 404
        assert (await client.post("/session/nope/turn", json={"transcript": "x"})).status_code == 404
        assert (await client.post("/session", json={"topic_id": "nope"})).status_code == 404
