"use client";

import type { VoiceState } from "./Waveform";

// One affordance: tap to start listening, tap again to send. Disabled while
// the tutor is thinking or speaking (no barge-in in the MVP).
export default function TalkButton({
  state,
  sttSupported,
  onStart,
  onStop,
}: {
  state: VoiceState;
  sttSupported: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const busy = state === "thinking" || state === "speaking";
  const listening = state === "listening";
  const label = !sttSupported
    ? "Mic not supported here — type below"
    : listening
      ? "Tap when you're done"
      : busy
        ? state === "thinking"
          ? "Thinking…"
          : "Speaking…"
        : "Tap to talk";

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        disabled={busy || !sttSupported}
        onClick={listening ? onStop : onStart}
        aria-pressed={listening}
        className={[
          "relative h-28 w-28 md:h-36 md:w-36 rounded-full transition-all duration-200 select-none",
          "flex items-center justify-center text-4xl md:text-5xl",
          "shadow-[0_0_0_8px_rgba(255,255,255,0.04)]",
          listening
            ? "bg-emerald-500 text-black scale-105 shadow-[0_0_60px_rgba(52,211,153,0.5)]"
            : busy
              ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
              : "bg-zinc-100 text-black hover:scale-105 active:scale-95",
        ].join(" ")}
      >
        {listening ? "■" : "🎙"}
        {listening && <span className="absolute inset-0 rounded-full animate-ping bg-emerald-400/30" />}
      </button>
      <div className="text-sm text-zinc-400 h-5">{label}</div>
    </div>
  );
}
