# Teach — voice-first Socratic tutor (hackathon MVP)

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

Optional — local text-to-speech (recommended; the browser voice is the fallback):

```bash
.venv/Scripts/pip install -e ".[tts]"
.venv/Scripts/python scripts/download_tts_models.py            # Piper voices (~60 MB each)
.venv/Scripts/python scripts/download_tts_models.py --kokoro   # + Kokoro-82M (~340 MB)
```

`.env` options:

| Var | Meaning |
|---|---|
| `GRADER_PROVIDER`, `TUTOR_PROVIDER` | `claude` or `ollama`, per role. |
| `OLLAMA_MODEL` | Default for both roles: `gemma4:31b-cloud`. Override per role with `OLLAMA_GRADER_MODEL` / `OLLAMA_TUTOR_MODEL`. Models must be pulled; `:cloud` models need `ollama signin`. |
| `OLLAMA_GRADER_THINK` | Unset = model default. Nemotron needs thinking to grade reliably (22 s/grade); Gemma does not (0.8 s). |
| `ANTHROPIC_API_KEY`, `TUTOR_MODEL` | For the Claude backends (`claude-opus-5`; effort tuned per route in code). |
| `MOCK_LLM=1` | Deterministic keyword grader + template tutor. No models, no cost — for UI work and demos. |
| `TTS_ENGINE` | `browser` (Web Speech API in the kiosk), `piper` or `kokoro` (server-side, `POST /tts`). |
| `PIPER_VOICE`, `KOKORO_VOICE`, `TTS_SPEED` | Default voice and rate. The kiosk header has a voice picker for any voice in `models/`. |

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
.venv/Scripts/python tests/evals/grader/run_evals.py --repeat 3   # grader eval set against the configured grader
OLLAMA_MODEL=nemotron-3-super:cloud .venv/Scripts/python tests/evals/grader/run_evals.py   # ...or any other model
.venv/Scripts/python tests/evals/tutor/bench_tutor.py --models gemma4:31b-cloud nemotron-3-super:cloud
```

The eval set (`tests/evals/grader/cases/`) is the thing that proves the grader is trustworthy: beginner vs advanced transcripts, a confident wrong answer, a stated misconception, vague name-dropping that must *not* verify, and STT-noisy speech that *must* verify. `--repeat 3` also checks that the same transcript gets the same verdicts every time. Every live grader call is captured to `tests/evals/grader/captured/` to seed more cases.

## Model comparison (2026-09-18, Ollama cloud models, same prompts)

**Grader** — 8 cases × 3 runs, strict expectations (name-dropping must be NOT_MENTIONED):

| model | thinking | pass | consistent across 3 runs | median latency | output tokens |
|---|---|---|---|---|---|
| `gemma4:31b-cloud` | no | **28/28** | yes | **0.8 s** | ~260 |
| `nemotron-3-super:cloud` | yes (default) | 28/28 | yes | 22 s | ~2,150 |
| `nemotron-3-super:cloud` | off | 23/28 | — | 5.5 s | — |
| `claude-opus-5` | adaptive | not run (no API credits) | | | |

Nemotron is only reliable with its reasoning on, which costs ~22 s per grade. Gemma reaches the same 28/28 without reasoning at under a second, after one prompt fix: an explicit "name-dropping is not evidence" rule with an example (it initially awarded PARTIAL to bare mentions).

**Tutor voice** — five scripted directives (introduce, continue, forced teach-back, failed teach-back, complete):

| model | first token | total | avg words | ends with a question | sentinel correct | leaks marker |
|---|---|---|---|---|---|---|
| `gemma4:31b-cloud` | **0.87 s** | 1.33 s | 80 | 5/5 | 5/5 | 0/5 |
| `nemotron-3-super:cloud` | 2.74 s | 3.73 s | 54 | 3/5 | 5/5 | 0/5 |

Gemma also reads better: it names what the student got right, what is missing, gives one example and asks one question. Both defaults are therefore `gemma4:31b-cloud`; a full turn (grade + first spoken sentence) now lands in ~3–4 s.

**TTS** — CPU only (4-core laptop, no VNNI), RTF = synthesis time ÷ audio length, lower is better:

| engine / voice | RTF | notes |
|---|---|---|
| Piper `*-medium` (jenny_dioco, hfc_female, amy, alba, alan, lessac) | **0.14** | default `en_GB-jenny_dioco-medium`; first words < 0.5 s |
| Piper `en_GB-cori-high` | 1.32 | too slow here |
| Kokoro-82M fp32 | 1.30 | more natural, but slower than real time on this CPU |
| Kokoro fp16 / int8 | 1.14 / 3.4 | no help on CPU without VNNI |

Kokoro is wired in (`TTS_ENGINE=kokoro`) for machines with a GPU or a faster CPU; Piper is the default. Server-side TTS synthesises one sentence per request and the kiosk pipelines them, so playback starts on the first sentence while the tutor is still streaming.

## How it works

The LLM is a component inside a **code-owned state machine** — it never decides the flow.

```
DIAGNOSTIC ──(grade)──► node selector picks deepest unverified node ──► INSTRUCT
INSTRUCT   ──(tutor turn; ends with <<TEACH_BACK>> when ready)──────► TEACH_BACK
TEACH_BACK ──(grade target node)──► VERIFIED → ledger event, next node → INSTRUCT
                                  └ not yet → retry (max 2), then park → INSTRUCT
nothing left ──► COMPLETE
```

Two LLM roles sharing one system prefix (the knowledge tree - prompt-cached on Claude):

| Role | Call | Output | Why separate |
|---|---|---|---|
| **Grader** | Claude: `messages.parse()` structured output, effort `high`. Ollama: same prompt + JSON-schema `format`, `temperature=0`, one corrective retry | per-node `VERIFIED / PARTIAL / GAP` + evidence quote | strict, deterministic, testable; anchored to each node's `rubric`, never free text |
| **Tutor voice** | Claude: `messages.stream()`, effort `low`. Ollama: streamed, `think=False` | ≤120 spoken words, one question | fast and conversational; receives a per-turn *directive* as a mid-conversation system message |

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
- `apps/web/lib/speech.ts` — `Listener` / `Speaker` interfaces; `ServerSpeaker` already streams Piper/Kokoro audio per sentence; Deepgram STT would slot in the same way.
- The FastAPI service is the place server-side audio streaming (WebSocket) lands — same process, no rewrite.
