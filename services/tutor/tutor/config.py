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
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    # Per-role overrides (default to OLLAMA_MODEL) so grader and tutor can differ.
    ollama_grader_model: str = os.getenv("OLLAMA_GRADER_MODEL") or os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    ollama_tutor_model: str = os.getenv("OLLAMA_TUTOR_MODEL") or os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    # Grader "thinking": unset -> model default (nemotron thinks, gemma does not).
    # Measured: nemotron needs it (22 s/grade, 28/28); with it off it becomes
    # unreliable (5 s, 23/28). gemma passes 28/28 without it at 0.8 s.
    ollama_grader_think: bool | None = (
        None if os.getenv("OLLAMA_GRADER_THINK", "") == "" else os.getenv("OLLAMA_GRADER_THINK") in {"1", "true", "yes"}
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    )
    # Server-side TTS: browser (client Web Speech API) | piper | kokoro
    tts_engine: str = os.getenv("TTS_ENGINE", "browser").lower()
    tts_models_dir: Path = Path(os.getenv("TTS_MODELS_DIR", str(Path(__file__).resolve().parents[1] / "models")))
    piper_voice: str = os.getenv("PIPER_VOICE", "en_GB-jenny_dioco-medium")
    kokoro_voice: str = os.getenv("KOKORO_VOICE", "af_heart")
    kokoro_model_file: str = os.getenv("KOKORO_MODEL_FILE", "kokoro-v1.0.onnx")
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))
    # Tutor pacing knobs (code-enforced, not prompt-enforced)
    max_instruct_turns_per_node: int = int(os.getenv("MAX_INSTRUCT_TURNS", "3"))
    max_teach_back_attempts: int = int(os.getenv("MAX_TEACH_BACK_ATTEMPTS", "2"))
    # Where grader calls are captured for the eval set
    capture_dir: Path = Path(__file__).resolve().parents[1] / "tests" / "evals" / "grader" / "captured"


settings = Settings()
