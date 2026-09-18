"""Integrity layer (Phase 2). Stub interface so the real speaker-verification
implementation (pyannote / SpeechBrain / vendor API) drops in without touching
the orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    match: bool
    score: float
    method: str


class SpeakerVerifier:
    async def enroll(self, student_id: str, audio: bytes) -> None: ...
    async def verify(self, student_id: str, audio: bytes) -> VerificationResult: ...


class StubVerifier(SpeakerVerifier):
    async def enroll(self, student_id: str, audio: bytes) -> None:
        return None

    async def verify(self, student_id: str, audio: bytes) -> VerificationResult:
        return VerificationResult(match=True, score=1.0, method="stub")
