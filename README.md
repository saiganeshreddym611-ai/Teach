# Socratic Voice Tutor — Hackathon MVP

Voice-first tutor that replaces snapshot exams with a continuous **mastery ledger**. The student says what they know; a grader maps it to a curriculum tree; the tutor teaches only the deepest missing concept; the student explains it back; mastery is recorded against the exact utterance that earned it.

MVP scope: **CA Final · Financial Reporting · Ind AS 115** (42 concept nodes across 3 levels).

```
apps/web            Next.js kiosk UI (talk button, waveform, transcript, mastery grid)
services/tutor      FastAPI orchestrator: state machine + grader + tutor voice + ledger
curriculum/         Knowledge tree JSON (the core asset - authored, versioned, rubric per node)
```

## Run it

Two processes. The UI talks to the API over HTTP/SSE.

**1. Tutor service (Python 3.12+)**

```bash
cd services/tutor
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"        # macOS/Linux: .venv/bin/pip
cp .env.example .env                        # then edit
.venv/Scripts/python -m uvicorn tutor.main:app --port 8000 --reload
```

`.env` options:

| Var | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Required for real grading/tutoring. |
| `MOCK_LLM=1` | Run the whole loop with a deterministic keyword grader and template tutor — no key, no cost. Use this for UI work and demos without credentials. |
| `TUTOR_MODEL` | Default `claude-opus-5`. Effort is tuned per route in code (grader `high`, tutor `low`). |

**2. Kiosk UI (Node 20+)**

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000
```

Open in **Chrome** — the MVP uses the Web Speech API for STT/TTS. There is a text box fallback for browsers without mic support.

From the Claude desktop app, `.claude/launch.json` defines both servers (`tutor-api`, `web`).

## Test it

```bash
cd services/tutor
.venv/Scripts/python -m pytest              # 26 tests: selector, ledger, sentinel filter, state machine, HTTP loop (mocked LLM)
.venv/Scripts/python tests/evals/grader/run_evals.py --repeat 3   # grader eval set - needs ANTHROPIC_API_KEY
```

The eval set (`tests/evals/grader/cases/`) is the thing that proves the grader is trustworthy: beginner vs advanced transcripts, a confident wrong answer, a stated misconception, vague name-dropping that must *not* verify, and STT-noisy speech that *must* verify. `--repeat 3` also checks that the same transcript gets the same verdicts every time. Every live grader call is captured to `tests/evals/grader/captured/` to seed more cases.

## How it works

The LLM is a component inside a **code-owned state machine** — it never decides the flow.

```
DIAGNOSTIC ──(grade)──► node selector picks deepest unverified node ──► INSTRUCT
INSTRUCT   ──(tutor turn; ends with <<TEACH_BACK>> when ready)──────► TEACH_BACK
TEACH_BACK ──(grade target node)──► VERIFIED → ledger event, next node → INSTRUCT
                                  └ not yet → retry (max 2), then park → INSTRUCT
nothing left ──► COMPLETE
```

Two LLM roles, both `claude-opus-5`, sharing one prompt-cached prefix (the knowledge tree):

| Role | Call | Output | Why separate |
|---|---|---|---|
| **Grader** | `messages.parse()` structured output, effort `high` | per-node `VERIFIED / PARTIAL / GAP` + evidence quote | strict, deterministic, testable; anchored to each node's `rubric`, never free text |
| **Tutor voice** | `messages.stream()`, effort `low` | ≤120 spoken words, one question | fast and conversational; receives a per-turn *directive* as a mid-conversation system message |

The **node selector** (`node_selector.py`) is pure code: walk L1 → L2 → L3 in document order, first node not VERIFIED. That is the pitch's "identify deepest missing node" step, deliberately not left to the model.

The **ledger** (`ledger.py`) is append-only. Mastery is a projection (last event per node). Every event carries `evidence_turn_id` → the transcript turn that earned it. That is the audit trail an employer or regulator would ask for.

## Why there is no RAG in the MVP (and where it goes later)

The grader must grade against a **fixed taxonomy** — the authored tree with a rubric per node. Retrieval can't produce a taxonomy, and grading against whatever chunks came back on a given run makes verdicts non-deterministic, which is disqualifying for something that claims to replace exams. At one-topic scale the whole standard fits in the cached prefix anyway.

RAG earns its place in Phase 2 as a *grounding and scaling* layer, keyed by node rather than by similarity search wherever possible:

- scaling to every CA paper (retrieve the material for the *current* node),
- **citable** explanations via Claude's citations feature (`source_refs` on each node already point at standard paragraphs),
- off-taxonomy student questions → answer, cite, and log the gap for curation,
- amendments (versioned corpus, no prompt rewrites),
- an **offline** pipeline that drafts nodes/rubrics from source material for a CA to review — how one topic becomes a syllabus.

Suggested shape: chunk by standard paragraph number (stable IDs), pgvector on Supabase, hybrid BM25 + vector.

## Phase 2 hooks already in the code

- `tutor/integrity.py` — `SpeakerVerifier` interface with a stub; drop in pyannote/SpeechBrain or a vendor API.
- `tutor/store.py` — `SessionStore` interface, in-memory now; Supabase tables `sessions / turns / ledger_events` next.
- `apps/web/lib/speech.ts` — `Listener` / `Speaker` interfaces; Deepgram + ElevenLabs replace Web Speech without touching `page.tsx`.
- The FastAPI service is the place server-side audio streaming (WebSocket) lands — same process, no rewrite.
