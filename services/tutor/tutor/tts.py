"""Server-side text-to-speech.

Two local engines behind one interface, chosen by TTS_ENGINE:

- piper  : VITS voices (~20M params). Very fast on CPU (RTF ~0.13 on a 4-core
           laptop). Natural enough for tutoring; the "efficient" choice.
- kokoro : Kokoro-82M via ONNX. Noticeably more natural, but ~10x the compute
           (RTF ~1.3 on the same laptop, i.e. slower than real time). Pick it on
           a faster CPU / GPU or when voice quality matters more than latency.

Both return 16-bit mono PCM; `wav_bytes` wraps it for the browser. Synthesis is
CPU-bound and synchronous - call it via asyncio.to_thread from the API.
"""
from __future__ import annotations

import io
import threading
import wave
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

from .config import settings


class TTSEngine(Protocol):
    name: str
    voice: str
    sample_rate: int

    def synth(self, text: str, speed: float = 1.0, voice: str | None = None) -> np.ndarray:  # int16 mono
        ...

    def voices(self) -> list[str]:
        ...

    def warm(self) -> None:
        ...


def wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.astype("<i2").tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------- #
class PiperEngine:
    name = "piper"

    def __init__(self, models_dir: Path, voice: str):
        from piper import PiperVoice, SynthesisConfig

        path = models_dir / f"{voice}.onnx"
        if not path.exists():
            raise FileNotFoundError(
                f"Piper voice not found: {path}. Run scripts/download_tts_models.py or "
                f"`python -m piper.download_voices --download-dir {models_dir} {voice}`"
            )
        self.models_dir = models_dir
        self.voice = voice
        self._PiperVoice = PiperVoice
        self._SynthesisConfig = SynthesisConfig
        self._loaded: dict[str, object] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._load_lock = threading.Lock()
        self.sample_rate = self._get(voice).config.sample_rate

    def voices(self) -> list[str]:
        return sorted(p.stem for p in self.models_dir.glob("*.onnx") if p.stem.startswith("en_") and (p.parent / f"{p.name}.json").exists())

    def warm(self) -> None:
        """Load every voice and run a tiny synth so the first real sentence in any
        voice is fast. Call from a background thread at startup."""
        for name in self.voices():
            try:
                self.synth("Ready.", voice=name)
            except Exception:
                pass

    def _get(self, name: str):
        with self._load_lock:
            v = self._loaded.get(name)
            if v is None:
                path = self.models_dir / f"{name}.onnx"
                if not path.exists():
                    raise FileNotFoundError(f"Piper voice not found: {path}")
                v = self._PiperVoice.load(path)
                self._loaded[name] = v
                self._locks[name] = threading.Lock()  # one ORT session per voice; serialise calls
            return v

    def synth(self, text: str, speed: float = 1.0, voice: str | None = None) -> np.ndarray:
        name = voice or self.voice
        v = self._get(name)
        self.sample_rate = v.config.sample_rate
        cfg = self._SynthesisConfig(length_scale=1.0 / max(speed, 0.25))
        with self._locks[name]:
            chunks = list(v.synthesize(text, syn_config=cfg))
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate([np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in chunks])


# --------------------------------------------------------------------------- #
class KokoroEngine:
    name = "kokoro"

    def __init__(self, models_dir: Path, voice: str, model_file: str):
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        model = models_dir / model_file
        voices = models_dir / "voices-v1.0.bin"
        for p in (model, voices):
            if not p.exists():
                raise FileNotFoundError(f"Kokoro file not found: {p}. Run scripts/download_tts_models.py")
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(str(model), sess_options=so, providers=["CPUExecutionProvider"])
        self._k = Kokoro.from_session(session, str(voices))
        self.voice = voice
        self.sample_rate = 24000
        self._lock = threading.Lock()

    def voices(self) -> list[str]:
        return [v for v in self._k.get_voices() if v[:1] in "ab"]  # English voices: a* = US, b* = GB

    def warm(self) -> None:
        self.synth("Ready.")

    def synth(self, text: str, speed: float = 1.0, voice: str | None = None) -> np.ndarray:
        name = voice or self.voice
        lang = "en-gb" if name.startswith("b") else "en-us"
        with self._lock:
            samples, sr = self._k.create(text, voice=name, speed=speed, lang=lang)
        self.sample_rate = sr
        return np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)


# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_tts() -> TTSEngine | None:
    """None when TTS_ENGINE=browser (client uses the Web Speech API)."""
    engine = settings.tts_engine
    if engine in {"browser", "none", ""}:
        return None
    models_dir = settings.tts_models_dir
    if engine == "piper":
        return PiperEngine(models_dir, settings.piper_voice)
    if engine == "kokoro":
        return KokoroEngine(models_dir, settings.kokoro_voice, settings.kokoro_model_file)
    raise ValueError(f"unknown TTS_ENGINE '{engine}' (expected browser | piper | kokoro)")


def describe_tts() -> dict:
    engine = settings.tts_engine
    if engine in {"browser", "none", ""}:
        return {"engine": "browser", "ready": False}
    try:
        tts = get_tts()
        return {"engine": tts.name, "voice": tts.voice, "sample_rate": tts.sample_rate, "ready": True, "voices": tts.voices()}
    except Exception as e:  # missing model files etc. - report, don't crash /health
        return {"engine": engine, "ready": False, "error": f"{type(e).__name__}: {e}"}
