"""Grader: student transcript + rubric -> structured verdicts.

Two implementations behind one interface:
- ClaudeGrader   : claude-opus-5, structured output, effort=high.
- MockGrader     : deterministic keyword overlap, for key-less UI/dev runs.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Protocol

from anthropic import AsyncAnthropic

from .config import settings
from .curriculum import Curriculum
from .models import GraderResult, NodeStatus, NodeVerdict
from .prompts import GRADER_INSTRUCTIONS, tree_block


class Grader(Protocol):
    async def grade(
        self,
        curriculum: Curriculum,
        transcript: str,
        *,
        focus_node_id: str | None,
        prior_context: str,
        session_id: str,
    ) -> GraderResult: ...


def _user_content(curriculum: Curriculum, transcript: str, focus_node_id: str | None, prior_context: str) -> str:
    if focus_node_id:
        node = curriculum.node(focus_node_id)
        focus = (
            "<focus>\nThis is a TEACH-BACK. The student was asked to explain the node "
            f"`{node.id}` (\"{node.title}\") in their own words.\n"
            f"You MUST return a verdict for `{node.id}`. Also return verdicts for any other nodes "
            "the student's words give evidence for.\n</focus>\n"
        )
    else:
        focus = (
            "<focus>\nThis is the BASELINE DIAGNOSTIC. The student was asked to say everything they know "
            "about the topic. Return verdicts for every node their words give evidence for (VERIFIED, PARTIAL or GAP).\n</focus>\n"
        )
    prior = f"<prior_context>\n{prior_context}\n</prior_context>\n" if prior_context else ""
    return f"{focus}{prior}<student_transcript>\n{transcript}\n</student_transcript>"


class ClaudeGrader:
    def __init__(self, client: AsyncAnthropic | None = None):
        self.client = client or AsyncAnthropic()

    async def grade(self, curriculum, transcript, *, focus_node_id, prior_context, session_id) -> GraderResult:
        user = _user_content(curriculum, transcript, focus_node_id, prior_context)
        response = await self.client.messages.parse(
            model=settings.model,
            max_tokens=16000,
            system=[tree_block(curriculum), {"type": "text", "text": GRADER_INSTRUCTIONS}],
            messages=[{"role": "user", "content": user}],
            output_format=GraderResult,
            output_config={"effort": "high"},
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"grader refused: {response.stop_details}")
        result: GraderResult | None = response.parsed_output
        if result is None:
            raise RuntimeError(f"grader returned no parsed output (stop_reason={response.stop_reason})")
        # Drop verdicts for ids not in the tree (defensive; the schema can't enforce membership).
        result.verdicts = [v for v in result.verdicts if v.node_id in curriculum.by_id]
        _capture(session_id, user, result, response)
        return result


def _capture(session_id: str, user: str, result: GraderResult, response) -> None:
    """Every grader call is an eval candidate. Write it to disk."""
    try:
        settings.capture_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        payload = {
            "session_id": session_id,
            "request_id": getattr(response, "_request_id", None),
            "model": response.model,
            "usage": response.usage.model_dump() if response.usage else None,
            "input": user,
            "output": result.model_dump(),
        }
        (settings.capture_dir / f"{ts}_{session_id}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:  # capture must never break grading
        pass


# --------------------------------------------------------------------------- #
# Mock
# --------------------------------------------------------------------------- #
_STOP = {
    "the", "and", "that", "with", "from", "this", "when", "than", "then", "into", "only", "over",
    "each", "must", "have", "been", "which", "their", "there", "these", "those", "about", "after",
    "before", "other", "some", "such", "also", "more", "less", "does", "were", "step", "entity",
    "customer", "contract", "revenue", "goods", "services", "service", "good", "performance",
    "obligation", "obligations", "states", "explains", "names", "gives", "least", "mentions",
    "identifies", "distinguishes", "lists", "notes", "describes", "defines",
}


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in _STOP}


class MockGrader:
    """Keyword-overlap grader. Not clever - just deterministic and free."""

    async def grade(self, curriculum, transcript, *, focus_node_id, prior_context, session_id) -> GraderResult:
        said = _keywords(transcript)
        verdicts: list[NodeVerdict] = []
        for n in curriculum.tree.nodes:
            target = _keywords(n.title + " " + " ".join(n.rubric))
            if not target:
                continue
            overlap = len(said & target) / len(target)
            if overlap >= 0.45:
                status = NodeStatus.VERIFIED
            elif overlap >= 0.2:
                status = NodeStatus.PARTIAL
            elif n.id == focus_node_id:
                status = NodeStatus.GAP
            else:
                continue
            verdicts.append(
                NodeVerdict(
                    node_id=n.id,
                    status=status,
                    confidence=round(min(1.0, 0.5 + overlap), 2),
                    evidence=" ".join(sorted(said & target))[:120] or "(no matching terms)",
                )
            )
        verified = sum(1 for v in verdicts if v.status == NodeStatus.VERIFIED)
        summary = f"[mock] {verified} node(s) verified, {len(verdicts) - verified} partial/gap from keyword overlap."
        return GraderResult(verdicts=verdicts, summary=summary)
