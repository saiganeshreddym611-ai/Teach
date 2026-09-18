"""Grader: student transcript + rubric -> structured verdicts.

Three implementations behind one interface:
- ClaudeGrader   : claude-opus-5, structured output, effort=high.
- OllamaGrader   : any Ollama model (default gemma4:31b-cloud), JSON-schema output.
- MockGrader     : deterministic keyword overlap, for key-less UI/dev runs.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Protocol

from anthropic import AsyncAnthropic
from ollama import AsyncClient as OllamaAsyncClient
from ollama import ResponseError as OllamaResponseError

from .config import settings
from .curriculum import Curriculum
from .models import GraderResult, NodeStatus, NodeVerdict
from .prompts import GRADER_INSTRUCTIONS, tree_block


def _finalise(curriculum: Curriculum, result: GraderResult) -> GraderResult:
    # Drop verdicts for ids not in the tree (defensive; no schema can enforce membership).
    result.verdicts = [v for v in result.verdicts if v.node_id in curriculum.by_id]
    return result


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
        result = _finalise(curriculum, result)
        _capture(
            session_id, user, result,
            provider="claude", model=response.model,
            request_id=getattr(response, "_request_id", None),
            usage=response.usage.model_dump() if response.usage else None,
        )
        return result


def _inline_schema(schema: dict) -> dict:
    """Resolve local $refs and forbid extra keys. Ollama cannot grammar-constrain
    cloud models, so the schema is advisory there - a flat, explicit one is
    followed far more reliably than one full of $defs."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            out = {k: walk(v) for k, v in node.items() if k != "$defs"}
            if out.get("type") == "object" and "properties" in out:
                out.setdefault("additionalProperties", False)
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


def _extract_json(text: str) -> str:
    """Tolerate the two most common wrappers models add around JSON: markdown
    code fences and prose before/after the object. Anything else still fails
    validation and triggers the corrective retry."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
        t = t.strip()
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    # Take the first complete JSON object; ignore prose before it and anything
    # after it (some models keep talking, or emit the object twice).
    a = t.find("{")
    if a != -1:
        try:
            _, end = json.JSONDecoder().raw_decode(t, a)
            return t[a:end]
        except ValueError:
            pass
    return t


OLLAMA_OUTPUT_CONTRACT = """
Output format - return ONLY a JSON object of exactly this shape, nothing else:
{"verdicts": [{"node_id": "<id from the tree>", "status": "VERIFIED|PARTIAL|GAP|NOT_MENTIONED", "confidence": 0.0-1.0, "evidence": "<= 25 words"}], "summary": "<one sentence>"}
- "verdicts" is a list, never an object keyed by node id.
- "status" is exactly one of VERIFIED, PARTIAL, GAP, NOT_MENTIONED.
- Do not add keys that are not in the shape above.
"""


class OllamaGrader:
    """Same prompts as ClaudeGrader, sent to an Ollama model with the GraderResult
    JSON schema as `format` plus an explicit shape contract. temperature=0 for
    repeatable verdicts. One corrective retry if the shape is wrong."""

    def __init__(self, client: OllamaAsyncClient | None = None, model: str | None = None):
        self.client = client or OllamaAsyncClient(host=settings.ollama_host)
        self.model = model or settings.ollama_grader_model
        self.schema = _inline_schema(GraderResult.model_json_schema())

    async def _chat(self, messages: list[dict]):
        kw = {} if settings.ollama_grader_think is None else {"think": settings.ollama_grader_think}
        for attempt in (1, 2):
            try:
                return await self.client.chat(
                    model=self.model,
                    messages=messages,
                    format=self.schema,
                    options={"temperature": 0, "num_ctx": 32768},
                    **kw,
                )
            except OllamaResponseError as e:
                # :cloud models occasionally 502 on a TLS/proxy hiccup; one retry clears it.
                if attempt == 2 or (e.status_code or 500) < 500:
                    raise
            except (ConnectionError, TimeoutError):
                if attempt == 2:
                    raise

    async def grade(self, curriculum, transcript, *, focus_node_id, prior_context, session_id) -> GraderResult:
        user = _user_content(curriculum, transcript, focus_node_id, prior_context)
        system = tree_block(curriculum)["text"] + "\n\n" + GRADER_INSTRUCTIONS + OLLAMA_OUTPUT_CONTRACT
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        response = await self._chat(messages)
        content = response.message.content or ""
        try:
            result = GraderResult.model_validate_json(_extract_json(content))
        except Exception as first_err:
            # One corrective round-trip: show the model its own output and the error.
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    f"That output does not match the required shape ({type(first_err).__name__}). "
                    "Re-emit the same verdicts as a JSON object with a top-level \"verdicts\" LIST and a "
                    "\"summary\" string, exactly as specified in the output format. JSON only."
                )},
            ]
            response = await self._chat(messages)
            content = response.message.content or ""
            try:
                result = GraderResult.model_validate_json(_extract_json(content))
            except Exception as e:
                raise RuntimeError(f"ollama grader returned invalid JSON twice ({e}): {content[:300]}") from e
        result = _finalise(curriculum, result)
        _capture(
            session_id, user, result,
            provider="ollama", model=response.model, request_id=None,
            usage={"prompt_eval_count": response.prompt_eval_count, "eval_count": response.eval_count,
                   "total_ms": round((response.total_duration or 0) / 1e6), "retried": len(messages) > 2},
        )
        return result


def _capture(session_id: str, user: str, result: GraderResult, *, provider: str, model: str,
             request_id: str | None, usage: dict | None) -> None:
    """Every grader call is an eval candidate. Write it to disk."""
    try:
        settings.capture_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        payload = {
            "session_id": session_id,
            "provider": provider,
            "request_id": request_id,
            "model": model,
            "usage": usage,
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
