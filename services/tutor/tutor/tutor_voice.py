"""Tutor voice: streams the next spoken turn.

Yields text deltas. The caller strips the TEACH_BACK sentinel and turns it into
a flag; the model never sees ledger state except via the directive.
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from anthropic import AsyncAnthropic
from ollama import AsyncClient as OllamaAsyncClient
from ollama import ResponseError as OllamaResponseError

from .config import settings
from .curriculum import Curriculum
from .models import Session
from .prompts import TEACH_BACK_SENTINEL, TUTOR_INSTRUCTIONS, tree_block


class TutorVoice(Protocol):
    def stream(self, curriculum: Curriculum, session: Session, directive: str) -> AsyncIterator[str]: ...


def _history(session: Session) -> list[dict]:
    """Student -> user, tutor -> assistant. Drop leading tutor turns (the static
    opening prompt) so the first message is a user message."""
    msgs: list[dict] = []
    for t in session.turns:
        role = "user" if t.role == "student" else "assistant"
        if not msgs and role == "assistant":
            continue
        msgs.append({"role": role, "content": t.text})
    return msgs


class ClaudeTutor:
    def __init__(self, client: AsyncAnthropic | None = None):
        self.client = client or AsyncAnthropic()

    async def stream(self, curriculum, session, directive) -> AsyncIterator[str]:
        messages = _history(session)
        # Mid-conversation system message: operator channel, keeps the cached
        # history prefix intact, and student text cannot impersonate it.
        messages.append({"role": "system", "content": directive})
        async with self.client.messages.stream(
            model=settings.model,
            max_tokens=4096,
            system=[tree_block(curriculum), {"type": "text", "text": TUTOR_INSTRUCTIONS}],
            messages=messages,
            output_config={"effort": "low"},
        ) as stream:
            async for text in stream.text_stream:
                yield text


class OllamaTutor:
    """Same prompts as ClaudeTutor, streamed from an Ollama model. The directive
    still travels as a trailing system message (Nemotron honours it); thinking
    is switched off so reasoning never reaches the speaker. Slightly warm
    temperature so explanations don't read as canned."""

    def __init__(self, client: OllamaAsyncClient | None = None, model: str | None = None):
        self.client = client or OllamaAsyncClient(host=settings.ollama_host)
        self.model = model or settings.ollama_tutor_model

    async def stream(self, curriculum, session, directive) -> AsyncIterator[str]:
        system = tree_block(curriculum)["text"] + "\n\n" + TUTOR_INSTRUCTIONS
        messages = [{"role": "system", "content": system}, *_history(session), {"role": "system", "content": directive}]
        for attempt in (1, 2):
            yielded = False
            try:
                async for chunk in await self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True,
                    think=False,
                    options={"temperature": 0.3, "num_ctx": 32768, "num_predict": 400},
                ):
                    text = chunk.message.content
                    if text:
                        yielded = True
                        yield text
                return
            except OllamaResponseError as e:
                # Retry only if nothing reached the speaker yet (a 502 before first token).
                if yielded or attempt == 2 or (e.status_code or 500) < 500:
                    raise
            except (ConnectionError, TimeoutError):
                if yielded or attempt == 2:
                    raise


def _short_title(title: str) -> str:
    # "Step 4 — Allocate ..." -> "Allocate ..."
    return title.split("—")[-1].strip()


class MockTutor:
    """Template tutor for key-less runs. Reads the directive for what to do."""

    async def stream(self, curriculum, session, directive) -> AsyncIterator[str]:
        node = curriculum.node(session.target_node) if session.target_node else None
        if "PHASE=COMPLETE" in directive:
            text = (
                "That is everything on this topic for today. You have verified every core concept "
                "in the ledger. Well done. Shall we pick the next standard?"
            )
        elif node is None:
            text = "Thanks. Let's begin. What would you like to start with?"
        elif "ACTION=REQUEST_TEACH_BACK" in directive or "ACTION=CONTINUE" in directive:
            text = (
                f"Good. Now explain {_short_title(node.title)} back to me in your own words, "
                f"with one example. {TEACH_BACK_SENTINEL}"
            )
        elif "TEACH_BACK_FAILED" in directive:
            first_sentence = node.canonical_explanation.split(". ")[0]
            text = (
                f"Not quite yet. The key point is this: {first_sentence}. "
                f"Try once more: how would you explain it to a colleague? {TEACH_BACK_SENTINEL}"
            )
        else:
            example = node.example if node.example else "Think of any contract you know."
            text = (
                f"Let's look at {_short_title(node.title)}. {node.canonical_explanation} "
                f"For example: {example} Does that make sense so far?"
            )
        # Stream in small chunks so client-side sentence queueing is exercised.
        for i in range(0, len(text), 24):
            yield text[i : i + 24]
