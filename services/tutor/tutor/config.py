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
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )
    # Tutor pacing knobs (code-enforced, not prompt-enforced)
    max_instruct_turns_per_node: int = int(os.getenv("MAX_INSTRUCT_TURNS", "3"))
    max_teach_back_attempts: int = int(os.getenv("MAX_TEACH_BACK_ATTEMPTS", "2"))
    # Where grader calls are captured for the eval set
    capture_dir: Path = Path(__file__).resolve().parents[1] / "tests" / "evals" / "grader" / "captured"


settings = Settings()
