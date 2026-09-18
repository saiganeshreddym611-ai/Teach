"use client";

import type { MasteryEntry, NodeStatus } from "@/lib/api";

const STATUS_STYLE: Record<NodeStatus, string> = {
  VERIFIED: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  PARTIAL: "bg-amber-500/15 text-amber-200 border-amber-500/40",
  GAP: "bg-rose-500/15 text-rose-200 border-rose-500/40",
  NOT_MENTIONED: "bg-zinc-800/60 text-zinc-500 border-zinc-700/60",
};

const STATUS_DOT: Record<NodeStatus, string> = {
  VERIFIED: "bg-emerald-400",
  PARTIAL: "bg-amber-400",
  GAP: "bg-rose-400",
  NOT_MENTIONED: "bg-zinc-600",
};

function shortTitle(title: string) {
  return title.split("—").pop()!.trim();
}

// L1 rows, each with its L2 and L3 children as chips. The target node pulses.
export default function MasteryGrid({
  mastery,
  targetNode,
  summary,
}: {
  mastery: MasteryEntry[];
  targetNode: string | null;
  summary: string;
}) {
  const level1 = mastery.filter((m) => m.level === 1);
  const childrenOf = (id: string) => mastery.filter((m) => m.parent === id);
  const verified = mastery.filter((m) => m.status === "VERIFIED").length;
  const pct = mastery.length ? Math.round((verified / mastery.length) * 100) : 0;

  return (
    <aside className="flex flex-col gap-4 h-full min-h-0">
      <div>
        <div className="flex items-baseline justify-between">
          <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500">Mastery ledger</h2>
          <span className="text-sm text-zinc-300 tabular-nums">
            {verified}/{mastery.length} · {pct}%
          </span>
        </div>
        <div className="mt-2 h-1.5 w-full rounded bg-zinc-800 overflow-hidden">
          <div className="h-full bg-emerald-400 transition-all duration-700" style={{ width: `${pct}%` }} />
        </div>
        {summary && <p className="mt-2 text-xs text-zinc-400 leading-snug">{summary}</p>}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-3">
        {level1.map((l1) => (
          <div key={l1.node_id} className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-3">
            <div className="flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${STATUS_DOT[l1.status]}`} />
              <span
                className={[
                  "text-sm font-medium",
                  l1.status === "VERIFIED" ? "text-emerald-100" : "text-zinc-200",
                  targetNode === l1.node_id ? "animate-pulse" : "",
                ].join(" ")}
              >
                {l1.title}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {childrenOf(l1.node_id).map((c) => (
                <span
                  key={c.node_id}
                  title={`${c.title} — ${c.status}${c.confidence != null ? ` (${Math.round(c.confidence * 100)}%)` : ""}`}
                  className={[
                    "rounded-md border px-2 py-0.5 text-[11px] leading-5 whitespace-nowrap",
                    STATUS_STYLE[c.status],
                    c.level === 3 ? "opacity-80" : "",
                    targetNode === c.node_id ? "ring-2 ring-sky-400/70 animate-pulse" : "",
                  ].join(" ")}
                >
                  {c.level === 3 && <span className="text-zinc-500 mr-1">L3</span>}
                  {shortTitle(c.title)}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-3 text-[10px] text-zinc-500">
        {(["VERIFIED", "PARTIAL", "GAP", "NOT_MENTIONED"] as NodeStatus[]).map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${STATUS_DOT[s]}`} />
            {s === "NOT_MENTIONED" ? "pending" : s.toLowerCase()}
          </span>
        ))}
      </div>
    </aside>
  );
}
