"""Factory: real Claude clients or mocks, chosen by MOCK_LLM."""
from __future__ import annotations

from functools import lru_cache

from .config import settings
from .grader import ClaudeGrader, Grader, MockGrader, OllamaGrader
from .tutor_voice import ClaudeTutor, MockTutor, OllamaTutor, TutorVoice


@lru_cache(maxsize=1)
def get_grader() -> Grader:
    if settings.mock_llm:
        return MockGrader()
    if settings.grader_provider == "ollama":
        return OllamaGrader()
    return ClaudeGrader()


def describe_grader() -> str:
    if settings.mock_llm:
        return "mock"
    if settings.grader_provider == "ollama":
        return f"ollama:{settings.ollama_model}"
    return f"claude:{settings.model}"


@lru_cache(maxsize=1)
def get_tutor() -> TutorVoice:
    if settings.mock_llm:
        return MockTutor()
    if settings.tutor_provider == "ollama":
        return OllamaTutor()
    return ClaudeTutor()


def describe_tutor() -> str:
    if settings.mock_llm:
        return "mock"
    if settings.tutor_provider == "ollama":
        return f"ollama:{settings.ollama_model}"
    return f"claude:{settings.model}"
