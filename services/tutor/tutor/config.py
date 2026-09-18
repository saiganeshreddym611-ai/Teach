"""Environment-driven settings."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@dataclass
class Settings:
    model: str = os.getenv("TUTOR_MODEL", "claude-opus-5")
    mock_llm: bool = os.getenv("MOCK_LLM", "0") in {"1", "true", "yes"}
    # Backends: "claude" (default) or "ollama", per role. MOCK_LLM=1 overrides both.
    grader_provider: str = os.getenv("GRADER_PROVIDER", "claude").lower()
    tutor_provider: str = os.getenv("TUTOR_PROVIDER", "claude").lower()
    ollama_model: str = os.getenv("OLLAMA_MODEL", "nemotron-3-super:cloud")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )
    # Tutor pacing knobs (code-enforced, not prompt-enforced)
    max_instruct_turns_per_node: int = int(os.getenv("MAX_INSTRUCT_TURNS", "3"))
    max_teach_back_attempts: int = int(os.getenv("MAX_TEACH_BACK_ATTEMPTS", "2"))
    # Where grader calls are captured for the eval set
    capture_dir: Path = Path(__file__).resolve().parents[1] / "tests" / "evals" / "grader" / "captured"


settings = Settings()
