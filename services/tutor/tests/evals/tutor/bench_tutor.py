"""Benchmark tutor-voice models on a fixed scripted session.

    python tests/evals/tutor/bench_tutor.py --models nemotron-3-super:cloud gemma4:31b-cloud

For each model, replays the same five directives the state machine produces
(introduce, continue, forced teach-back, failed teach-back, complete) against a
canned history and reports, per turn:
  first-token latency, total time, word count (<=120 rule), question at end,
  sentinel present exactly when required, sentinel never mentioned to student.
Prints the spoken text so quality can be eyeballed. Ollama only (Claude tutor
needs credits); uses the same OllamaTutor class as production.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from tutor.curriculum import load_curriculum  # noqa: E402
from tutor.models import GraderResult, NodeStatus, NodeVerdict, Phase, Session, Turn  # noqa: E402
from tutor.prompts import TEACH_BACK_SENTINEL  # noqa: E402
from tutor.state_machine import SentinelFilter, _complete, _continue, _introduce, _teach_back_failed  # noqa: E402
from tutor.tutor_voice import OllamaTutor  # noqa: E402

DIAG = (
    "The first step is identifying the contract with the customer, an agreement creating enforceable rights "
    "and obligations. Second step is identifying the performance obligations. Third is the transaction price. "
    "Fifth is recognising revenue when control transfers."
)


def make_session() -> Session:
    s = Session(student_id="bench", topic_id="ind_as_115")
    s.turns.append(Turn(role="student", text=DIAG, phase=Phase.DIAGNOSTIC))
    s.student_level_summary = "Knows steps 1, 2, 3 and 5 by name; step 4 not mentioned."
    s.target_node = "ind_as_115.step_4"
    s.phase = Phase.INSTRUCT
    return s


def scripted_turns(curriculum):
    """(label, session, directive, sentinel_required)"""
    s1 = make_session()
    d1 = _introduce(curriculum, s1, "ind_as_115.step_4", preface="")

    s2 = make_session()
    s2.turns.append(Turn(role="tutor", text="Step 4 is allocation on relative standalone selling prices. Does that make sense?", phase=Phase.INSTRUCT))
    s2.turns.append(Turn(role="student", text="So it's based on what each item sells for alone, not the contract line?", phase=Phase.INSTRUCT))
    s2.instruct_turns_on_node = 1
    d2 = _continue(curriculum, s2, force_teach_back=False)

    s3 = make_session()
    s3.turns.extend(s2.turns[1:])
    s3.turns.append(Turn(role="tutor", text="Exactly, standalone prices, not contract labels. Why might that matter?", phase=Phase.INSTRUCT))
    s3.turns.append(Turn(role="student", text="Because labels can be gamed.", phase=Phase.INSTRUCT))
    s3.instruct_turns_on_node = 3
    d3 = _continue(curriculum, s3, force_teach_back=True)

    s4 = make_session()
    s4.turns.append(Turn(role="tutor", text="Explain step 4 back to me with an example.", phase=Phase.INSTRUCT))
    s4.turns.append(Turn(role="student", text="You split the price by what each item cost to make.", phase=Phase.TEACH_BACK))
    res = GraderResult(verdicts=[NodeVerdict(node_id="ind_as_115.step_4", status=NodeStatus.GAP, confidence=0.9, evidence="by what each item cost to make")], summary="wrong basis")
    d4 = _teach_back_failed(curriculum, s4, res, attempt=1)

    s5 = make_session()
    s5.phase = Phase.COMPLETE
    s5.target_node = None
    d5 = _complete(curriculum, s5)

    return [
        ("introduce", s1, d1, False),
        ("continue", s2, d2, None),      # model's discretion
        ("force_teach_back", s3, d3, True),
        ("teach_back_failed", s4, d4, True),
        ("complete", s5, d5, False),
    ]


async def bench_model(model: str, curriculum, show: bool) -> dict:
    tutor = OllamaTutor(model=model)
    rows = []
    for label, session, directive, need_sentinel in scripted_turns(curriculum):
        filt = SentinelFilter()
        t0 = time.perf_counter()
        first = None
        raw = []
        async for delta in tutor.stream(curriculum, session, directive):
            if first is None:
                first = time.perf_counter() - t0
            raw.append(delta)
        total = time.perf_counter() - t0
        raw_text = "".join(raw)
        spoken = "".join(filt.feed(d) for d in raw) + filt.flush()
        spoken = spoken.strip()
        words = len(spoken.split())
        ends_q = spoken.rstrip().endswith("?")
        mentions = bool(re.search(r"marker|token|<<|TEACH_BACK", spoken, re.I))
        ok_sentinel = True if need_sentinel is None else (filt.found == need_sentinel)
        rows.append({
            "turn": label, "first_s": round(first or 0, 2), "total_s": round(total, 2), "words": words,
            "ends_with_question": ends_q, "sentinel": filt.found, "sentinel_ok": ok_sentinel,
            "leaks_marker": mentions, "text": spoken, "raw_tail": raw_text[-40:],
        })
        if show:
            print(f"\n  [{label}] {first or 0:.2f}s/{total:.2f}s {words}w q={ends_q} sent={filt.found} ok={ok_sentinel} leak={mentions}")
            print("   " + spoken.replace("\n", " "))
    return {"model": model, "turns": rows}


async def main(models: list[str], show: bool) -> None:
    curriculum = load_curriculum("ind_as_115")
    results = []
    for m in models:
        print(f"\n== {m}")
        results.append(await bench_model(m, curriculum, show))
    print("\n\n| model | avg first-token | avg total | avg words | >120w | ends w/ ? | sentinel ok | marker leak |")
    print("|---|---|---|---|---|---|---|---|")
    for r in results:
        t = r["turns"]; n = len(t)
        print(f"| {r['model']} | {sum(x['first_s'] for x in t)/n:.2f}s | {sum(x['total_s'] for x in t)/n:.2f}s | "
              f"{sum(x['words'] for x in t)/n:.0f} | {sum(x['words']>120 for x in t)}/{n} | {sum(x['ends_with_question'] for x in t)}/{n} | "
              f"{sum(x['sentinel_ok'] for x in t)}/{n} | {sum(x['leaks_marker'] for x in t)}/{n} |")
    out = HERE / "results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["nemotron-3-super:cloud", "gemma4:31b-cloud"])
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.models, show=not a.quiet))
