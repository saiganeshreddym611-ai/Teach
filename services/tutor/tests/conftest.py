import pytest

from tutor.curriculum import load_curriculum
from tutor.models import GraderResult, NodeStatus, NodeVerdict, Session
from tutor.prompts import TEACH_BACK_SENTINEL


@pytest.fixture
def curriculum():
    return load_curriculum("ind_as_115")


@pytest.fixture
def session():
    return Session(student_id="s1", topic_id="ind_as_115")


class ScriptedGrader:
    """Returns the next scripted GraderResult on each call and records calls."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def grade(self, curriculum, transcript, *, focus_node_id, prior_context, session_id):
        self.calls.append({"transcript": transcript, "focus": focus_node_id, "prior": prior_context})
        return self.results.pop(0)


class ScriptedTutor:
    """Yields scripted text (optionally with the sentinel) and records directives."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.directives = []

    async def stream(self, curriculum, session, directive):
        self.directives.append(directive)
        text = self.scripts.pop(0)
        for i in range(0, len(text), 7):
            yield text[i : i + 7]


def verdict(node_id, status, conf=0.9, evidence="said it"):
    return NodeVerdict(node_id=node_id, status=NodeStatus(status), confidence=conf, evidence=evidence)


def result(*verdicts, summary="ok"):
    return GraderResult(verdicts=list(verdicts), summary=summary)


SENT = TEACH_BACK_SENTINEL
