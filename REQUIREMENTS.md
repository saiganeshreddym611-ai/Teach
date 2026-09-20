# Teach — Requirements Prompt for Code Agents

Source: `Pitch.pdf` (Voice-AI Educational Reform Startup Pitch, 2026-09-17), distilled into
requirements. Read this before changing product behaviour. When code and this document disagree,
raise it; do not silently pick one.

## 1. Vision (one paragraph)

A distraction-free, voice-first learning system that replaces high-stakes snapshot exams with
continuous, verified competency tracking. The student talks; an AI tutor diagnoses what they know,
teaches what they are missing Socratically, verifies understanding through teach-back, and records
every verified concept in an immutable **mastery ledger**. Over time the ledger, not an exam score,
is what employers and institutions trust. First domain: CA Final, Financial Reporting, Ind AS 115
(Revenue from Contracts with Customers).

## 2. Problems being solved

1. **Distraction.** Smart devices are built for media consumption; deep study on them is hard.
2. **Flawed testing.** Exams sample ~10% of a syllabus to judge the whole student; arbitrary
   pass/fail, high anxiety, and years of work can go in vain on one bad day.
3. **Passive learning.** Lectures give no real-time feedback; students discover gaps only after
   failing.

## 3. Solution layers

| Layer | Component | Function | MVP? |
|---|---|---|---|
| Hardware | Dedicated locked-down device | Zero-distraction execution boundary | No (Phase 2) |
| Software | Socratic voice tutor | Adaptive teaching + teach-back verification | **Yes** |
| Credentialing | Continuous knowledge ledger | Real-time matrix of mastered vs pending concepts | **Yes** |
| Integrity | Voice biometrics + fraud guard | Proves the ledger reflects the unassisted student | Mock only |
| Macro engine | Supply/demand data pipeline | Workforce capacity and educator planning | No (Phase 3) |

## 4. Core learning loop (the Feynman cycle)

Every session runs this loop. It is the product.

1. **Baseline diagnostic.** System: "Tell me everything you know about Ind AS 115." Student speaks
   freely (about 60 seconds, but unbounded).
2. **Syllabus mapping.** System maps the transcript onto the official curriculum, marks every
   accurately described concept, and identifies gaps and errors.
3. **Interactive instruction.** System teaches the missing concept by voice, step by step,
   Socratically, in under 90 seconds per turn.
4. **Teach-back verification.** System: "Now explain that back to me in your own words with an
   example." Student explains; system validates.
5. **Ledger update.** Verified concept is recorded in the student's immutable profile. Loop
   returns to step 3 with the next missing concept.

## 5. Functional requirements (MVP)

### FR-1 Voice-to-voice interface
- Full-screen kiosk UI, no navigation, one talk affordance, audio waveform visualiser.
- Speech-to-text for student input; text-to-speech for tutor output. Browser APIs are acceptable
  for the MVP; hosted STT/TTS (Deepgram, ElevenLabs) or local engines may replace them.
- Tutor speech must start before the full response has been generated (stream sentence by
  sentence). Target: first spoken sentence within a few seconds of the student finishing.

### FR-2 Hierarchical knowledge tree (not a linear script)
The curriculum is a three-level taxonomy so one flow serves beginners and advanced finalists.

```
Level 1: Macro structure     (the 5-step revenue model)
Level 2: Micro criteria      (specific technical parameters for each step)
Level 3: Advanced exceptions (contract modifications, variable consideration, warranties, ...)
```

Example for Step 1 (identify the contract):

| Level | Coverage |
|---|---|
| L1 | Says Step 1 is "identify the contract with the customer". |
| L2 | Details the 5 criteria: approval/commitment, identified rights, payment terms, commercial substance, collectability. |
| L3 | Explains contract modifications (prospective vs cumulative catch-up), combination of contracts, non-refundable upfront fees. |

Each node needs: id, level, parent, title, a grading rubric (what must be said to count),
known misconceptions, a canonical explanation, an example, and source references.

### FR-3 Grading (extract and map)
- Map every concept the student mentions to tree nodes.
- Status per node: `VERIFIED` (all rubric items evidenced accurately), `PARTIAL`, `GAP`
  (mentioned but wrong, or asked and not known), `NOT_MENTIONED`.
- Merely naming a topic is not evidence; the student must state the content.
- Grading must be strict, repeatable (same transcript, same verdicts) and produce structured
  output, never free text.
- Every verdict carries a confidence score and the evidence it rests on.

### FR-4 Deepest missing node selection
- After grading, pick the highest-priority unverified node, walking Level 1 first, then Level 2,
  then Level 3. This selection is deterministic code, not an LLM decision.
- Beginner who covers L1 partially and misses Steps 3–5 gets a macro drill ("You identified Steps
  1 and 2. Now let's look at Step 3...").
- Advanced finalist who covers all of L1 and parts of L2 gets a micro / L3 drill ("Great baseline.
  What happens if a contract modification occurs halfway?").

### FR-5 Adaptive tutor voice
- Shallow knowledge: simple, encouraging, core frameworks only.
- Deep knowledge: acknowledge fundamentals immediately, skip introductions, challenge with edge
  cases, exemptions and exam-level scenarios.
- One concept per turn, at most ~120 words, ends with a question. The tutor never grades and
  never writes to the ledger.

### FR-6 Teach-back
- After instruction, the tutor asks the student to explain the concept back with an example.
- The grader scores the teach-back against the target node's rubric.
- Pass: ledger records the node as verified. Fail: re-teach, bounded retries, then park the node as
  a gap and move on.

### FR-7 Mastery ledger
- Append-only events: `{student_id, node_id, status, confidence, evidence_turn_id, timestamp}`.
- Current mastery is a projection over events; a verified node is never silently downgraded.
- Every mastery claim must be traceable to the exact transcript turn that earned it.
- Reference shape from the pitch:

```json
{
  "student_id": "ca_final_001",
  "subject": "Financial Reporting",
  "standard": "Ind AS 115",
  "nodes": [
    {"concept_id": "step_1_contract_identification", "status": "MASTERED", "confidence_score": 0.92, "last_verified": "2026-09-15T12:00:00Z"},
    {"concept_id": "step_4_transaction_price_allocation", "status": "GAP_IDENTIFIED", "confidence_score": 0.45, "last_verified": "2026-09-15T12:02:00Z"}
  ]
}
```

### FR-8 Mastery dashboard
- Visual grid of the tree: L1 rows, L2/L3 chips, colour-coded verified / partial / gap / pending.
- Updates live as the session runs.

### FR-9 Voice verification (mock)
- Interface `verify(audio) -> {match, score}`. MVP returns a fixed match. Real acoustic
  fingerprinting is Phase 2. Keep it a swappable module.

## 6. Non-functional requirements

- **Flow is owned by code.** A state machine (DIAGNOSTIC → INSTRUCT ⇄ TEACH_BACK → COMPLETE)
  decides what happens; the LLM is a component called with a directive. The LLM never chooses
  the phase or the next node.
- **Auditability.** Log every grader call (input, rubric, output). These logs are the eval set.
- **Determinism where it matters.** Grader runs at temperature 0 with structured output; the tutor
  voice may be creative.
- **Latency.** Grade + first spoken sentence within a few seconds; instruction turns faster.
- **Distraction-free.** No navigation, notifications, links or secondary content on screen.
- **Portability.** Browser STT/TTS today; server-side streaming audio and on-device kiosk later
  without rewriting the orchestrator.

## 7. Out of scope for the MVP

- Locked-down device firmware / Android kiosk launcher.
- Real voice biometrics, speech-dynamics script detection, hardware air-gap.
- Full CA curriculum; only Ind AS 115.
- Employer skill-matrix API, certified skill profiles for job matching.
- Macro workforce engine (skill analytics dashboard, enrollment corridors, educator balancing).
- Professional-ethics scenario module (Socratic dilemmas for attitude and values).
- Persistent database (in-memory store is acceptable if the interface is swappable).

## 8. Roadmap (for context, not for MVP work)

| Phase | Target | Deliverable |
|---|---|---|
| 1 Hackathon MVP | CA Final FR, Ind AS 115 | Voice-to-voice web app: diagnostic, Socratic correction, mastery dashboard |
| 2 Product + hardware | Custom Android/Linux launcher on low-cost hardware | Full CA curricula; granular skill-mapping APIs for employers; real voice biometrics |
| 3 Reform + policy | Government bodies, higher-education institutions | Certified skill-matrix profiles replace exams; workforce capacity planning (±5% buffer corridors) |

Strategic alignment: competency-based education (NEP 2020), democratised 1-on-1 mentorship, and
direct hiring on granular proof of capability ("mastered 95% of complex financial instruments").

## 9. Job-scoped learning and demand-aware guidance (Phase 2-3 goal)

Stated in the founder's brief inside the pitch but absent from its structured sections. Treat it as
product direction that the MVP data model must not block.

- **Study only what the job needs.** A *job profile* is a set of tree nodes with a minimum depth
  for each. A student targeting a job studies that set, not the whole syllabus.
- **Adjacent fields to basic or integration depth only.** Areas outside the core of the job are
  required to Level 1, or to the specific nodes needed to work with the core, never to full depth.
- **Depth maps to role tier.** Deeper verified coverage (more Level 2 and Level 3 nodes) qualifies
  for higher-paid roles in the same field. The system shows the student which additional nodes
  unlock the next tier, so the incentive to go deeper is explicit and honest.
- **Multi-field jobs.** A job profile can span fields (for example Financial Reporting plus Audit).
  The ledger records every field, so eligibility is a set comparison, not a score.
- **Honest demand guidance.** Using workforce data (the Phase 3 macro engine), the system tells
  students plainly which sectors have demand, which are saturated, and what depth pays. Guidance
  must show the data behind it and must never hide oversupply to keep a student enrolled.

Implications for the data model (cheap to respect now):

- Keep node `level` as the depth tier. Add `job_profiles/*.json` later:
  `{job_id, title, sector, required: [{node_id, min_status}], adjacent: [{node_id, min_status}], pay_band}`.
- The ledger does not change. "Qualified for job X" is a projection: every required node is
  `VERIFIED`.
- The node selector gains an optional job-profile filter: walk only nodes in the profile, core
  before adjacent.
- Demand signals arrive as a read-only feed; guidance consumes them, never the grader.

Not in the MVP. One seeded job profile is acceptable for a demo if it costs nothing.

## 10. Acceptance criteria (demo script)

1. Start a session; the tutor asks the student to explain everything about Ind AS 115.
2. Student describes the five steps but omits Step 4 (allocation). Dashboard shows Steps 1, 2, 3, 5
   verified; Step 4 pending.
3. Tutor targets Step 4 and teaches allocation on relative standalone selling prices in under 90
   seconds, ending with a question.
4. Tutor asks for a teach-back with an example; student explains it correctly.
5. Step 4 turns verified; the ledger event references the teach-back turn.
6. Student gives a confident wrong teach-back (allocating on cost): node stays unverified, tutor
   corrects, bounded retries apply.
7. Same transcript graded three times yields identical statuses.

## 11. Constraints and open questions from the pitch

- Employers must be able to trust that the ledger reflects the unassisted student (motivates the
  integrity layer).
- Hiring is not only knowledge; attitude and ethics matter. Proposed answer: ethics scenarios in the
  same voice loop. Unresolved; not in MVP.
- Fairness across learner levels: the same opening prompt must work for a beginner and a finalist
  with several attempts behind them (motivates the three-level tree and adaptive tone).

## 12. Repository context

This repository already implements the MVP described above: `curriculum/ind_as_115.json`
(three-level tree), `services/tutor/` (FastAPI orchestrator, state machine, grader, tutor voice,
ledger, TTS) and `apps/web/` (Next.js kiosk). See `README.md` for how to run it and which models
and voices are configured. Use this document to judge whether a change serves the product; use
`README.md` and the code for how things are built.
