"use client";

import { useEffect, useRef } from "react";
import type { Phase } from "@/lib/api";

export interface LocalTurn {
  id: string;
  role: "student" | "tutor";
  text: string;
  phase?: Phase;
  streaming?: boolean;
}

export default function Transcript({ turns, interim }: { turns: LocalTurn[]; interim: string }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, interim]);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto pr-2 space-y-4">
      {turns.map((t) => (
        <div key={t.id} className={t.role === "student" ? "flex justify-end" : "flex justify-start"}>
          <div
            className={[
              "max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed",
              t.role === "student" ? "bg-emerald-500/15 text-emerald-50" : "bg-zinc-800/80 text-zinc-100",
            ].join(" ")}
          >
            <div className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
              {t.role === "student" ? "You" : "Tutor"}
              {t.phase && <span className="ml-2 text-zinc-600">{t.phase.toLowerCase().replace("_", " ")}</span>}
            </div>
            {t.text}
            {t.streaming && <span className="inline-block w-2 h-4 ml-1 bg-zinc-400 animate-pulse align-middle" />}
          </div>
        </div>
      ))}
      {interim && (
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-2xl px-4 py-3 text-[15px] bg-emerald-500/10 text-emerald-200/70 italic">
            {interim}
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
