"""Factory: real Claude clients or mocks, chosen by MOCK_LLM."""
from __future__ import annotations

from functools import lru_cache

from .config import settings
from .grader import ClaudeGrader, Grader, MockGrader
from .tutor_voice import ClaudeTutor, MockTutor, TutorVoice


@lru_cache(maxsize=1)
def get_grader() -> Grader:
    return MockGrader() if settings.mock_llm else ClaudeGrader()


@lru_cache(maxsize=1)
def get_tutor() -> TutorVoice:
    return MockTutor() if settings.mock_llm else ClaudeTutor()
