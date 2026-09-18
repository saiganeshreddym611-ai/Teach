"""FastAPI app: session routes (one SSE) plus server-side TTS."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse

from .config import settings
from .curriculum import load_curriculum
from .ledger import mastery_view
from .llm import describe_grader, describe_tutor, get_grader, get_tutor
from .models import (
    CreateSessionRequest,
    CreateSessionResponse,
    Phase,
    Session,
    SessionView,
    TTSRequest,
    Turn,
    TurnRequest,
)
from .state_machine import TurnEvent, run_turn
from .store import store
from .tts import describe_tts, get_tts, wav_bytes

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load TTS voices off the event loop so the first sentence of a session is fast.
    try:
        engine = get_tts()
    except Exception:
        engine = None
    if engine is not None:
        asyncio.get_running_loop().run_in_executor(None, engine.warm)
    yield


app = FastAPI(title="Socratic Tutor", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "mock_llm": settings.mock_llm,
        "grader": describe_grader(),
        "tutor": describe_tutor(),
        "tts": describe_tts(),
    }


@app.get("/tts/info")
async def tts_info() -> dict:
    return describe_tts()


@app.post("/tts")
async def tts(req: TTSRequest) -> Response:
    """Synthesise one sentence (the client sends sentences as the tutor streams)."""
    engine = get_tts()
    if engine is None:
        raise HTTPException(404, "server-side TTS is disabled (TTS_ENGINE=browser)")
    speed = req.speed or settings.tts_speed
    try:
        samples = await asyncio.to_thread(engine.synth, req.text, speed, req.voice)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return Response(
        content=wav_bytes(samples, engine.sample_rate),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-TTS-Engine": engine.name, "X-TTS-Voice": req.voice or engine.voice},
    )


@app.post("/session", response_model=CreateSessionResponse)
async def create_session(req: CreateSessionRequest) -> CreateSessionResponse:
    try:
        curriculum = load_curriculum(req.topic_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    session = Session(student_id=req.student_id, topic_id=req.topic_id)
    session.turns.append(Turn(role="tutor", text=curriculum.tree.opening_prompt, phase=Phase.DIAGNOSTIC))
    await store.save(session)
    return CreateSessionResponse(
        session_id=session.id, phase=session.phase, opening_prompt=curriculum.tree.opening_prompt
    )


@app.get("/session/{session_id}", response_model=SessionView)
async def get_session(session_id: str) -> SessionView:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    curriculum = load_curriculum(session.topic_id)
    return SessionView(
        session_id=session.id,
        student_id=session.student_id,
        topic_id=session.topic_id,
        phase=session.phase,
        target_node=session.target_node,
        student_level_summary=session.student_level_summary,
        mastery=mastery_view(session, curriculum),
        turns=session.turns,
        ledger=session.ledger,
    )


def _sse(event: TurnEvent) -> str:
    return f"event: {event.kind}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"


@app.post("/session/{session_id}/turn")
async def turn(session_id: str, req: TurnRequest) -> StreamingResponse:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    curriculum = load_curriculum(session.topic_id)

    async def gen() -> AsyncIterator[str]:
        try:
            async for ev in run_turn(session, req.transcript, curriculum, get_grader(), get_tutor()):
                yield _sse(ev)
        except Exception as e:  # surface to the client instead of a dropped stream
            yield _sse(TurnEvent("error", {"message": f"{type(e).__name__}: {e}"}))
        finally:
            await store.save(session)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
