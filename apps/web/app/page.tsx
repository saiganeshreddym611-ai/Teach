"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MasteryGrid from "@/components/MasteryGrid";
import TalkButton from "@/components/TalkButton";
import Transcript, { type LocalTurn } from "@/components/Transcript";
import Waveform, { type VoiceState } from "@/components/Waveform";
import { API_BASE, createSession, getSession, streamTurn, type MasteryEntry, type Phase } from "@/lib/api";
import { probeServerTTS, ServerSpeaker, WebSpeechListener, WebSpeechSpeaker, type Speaker } from "@/lib/speech";

const PHASE_LABEL: Record<Phase, string> = {
  DIAGNOSTIC: "Baseline diagnostic",
  INSTRUCT: "Instruction",
  TEACH_BACK: "Teach-back",
  COMPLETE: "Complete",
};

export default function Kiosk() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("DIAGNOSTIC");
  const [targetNode, setTargetNode] = useState<string | null>(null);
  const [turns, setTurns] = useState<LocalTurn[]>([]);
  const [mastery, setMastery] = useState<MasteryEntry[]>([]);
  const [summary, setSummary] = useState("");
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [interim, setInterim] = useState("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const speakingRef = useRef(false);
  const streamDoneRef = useRef(false);

  const maybeIdle = useCallback(() => {
    if (streamDoneRef.current && !speakingRef.current) setVoice("idle");
  }, []);

  // Speech objects live in refs (browser-only, mutable); only their
  // `supported` flag is needed for rendering, so it is mirrored into state.
  const listenerRef = useRef<WebSpeechListener | null>(null);
  const speakerRef = useRef<Speaker | null>(null);
  const [ttsLabel, setTtsLabel] = useState("browser voice");
  const [ttsVoices, setTtsVoices] = useState<string[]>([]);
  const [ttsVoice, setTtsVoice] = useState<string>("");
  // Lazy initialiser: false on the server, real value on the client. Nothing
  // on the pre-session screen depends on it, so hydration output is identical.
  const [sttSupported] = useState(() => new WebSpeechListener().supported);
  useEffect(() => {
    const listener = new WebSpeechListener();
    const speaker = new WebSpeechSpeaker((s) => {
      speakingRef.current = s;
      if (s) setVoice("speaking");
      else maybeIdle();
    });
    listenerRef.current = listener;
    speakerRef.current = speaker;
    return () => {
      speaker.cancel();
      listener.stop();
      listenerRef.current = null;
      speakerRef.current = null;
    };
  }, [maybeIdle]);

  const refreshMastery = useCallback(async (sid: string) => {
    const view = await getSession(sid);
    setMastery(view.mastery);
    setPhase(view.phase);
    setTargetNode(view.target_node);
    if (view.student_level_summary) setSummary(view.student_level_summary);
  }, []);

  const begin = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      const s = await createSession();
      setSessionId(s.session_id);
      setPhase(s.phase);
      setTurns([{ id: "opening", role: "tutor", text: s.opening_prompt, phase: s.phase }]);
      await refreshMastery(s.session_id);
      // Prefer the server engine (Piper/Kokoro) when the API has one loaded.
      const forceBrowser = process.env.NEXT_PUBLIC_TTS === "browser";
      const tts = forceBrowser ? null : await probeServerTTS(API_BASE);
      if (tts?.ready) {
        let remembered: string | null = null;
        try {
          remembered = localStorage.getItem("tts.voice");
        } catch {
          /* storage unavailable */
        }
        const chosen = remembered && tts.voices?.includes(remembered) ? remembered : (tts.voice ?? "");
        speakerRef.current?.cancel();
        speakerRef.current = new ServerSpeaker(
          API_BASE,
          (on) => {
            speakingRef.current = on;
            if (on) setVoice("speaking");
            else maybeIdle();
          },
          chosen || null,
        );
        setTtsLabel(tts.engine);
        setTtsVoices(tts.voices ?? []);
        setTtsVoice(chosen);
      }
      const speaker = speakerRef.current;
      if (speaker?.supported) {
        streamDoneRef.current = true;
        speaker.feed(s.opening_prompt);
        speaker.flush();
      }
    } catch (e) {
      setError(`Could not reach the tutor service. Is it running on port 8000? (${(e as Error).message})`);
    } finally {
      setStarting(false);
    }
  }, [refreshMastery, maybeIdle]);

  const submit = useCallback(
    async (transcript: string) => {
      if (!sessionId || !transcript.trim()) return;
      setError(null);
      setInterim("");
      const studentId = `s-${Date.now()}`;
      const tutorId = `t-${Date.now()}`;
      setTurns((t) => [...t, { id: studentId, role: "student", text: transcript, phase }]);
      setVoice("thinking");
      streamDoneRef.current = false;
      const speaker = speakerRef.current;
      speaker?.cancel();
      let started = false;

      await streamTurn(sessionId, transcript, {
        onGrade: (g) => {
          if (g.summary) setSummary(g.summary);
        },
        onText: (delta) => {
          if (!started) {
            started = true;
            setTurns((t) => [...t, { id: tutorId, role: "tutor", text: "", streaming: true }]);
            if (!speaker?.supported) setVoice("speaking");
          }
          setTurns((t) => t.map((x) => (x.id === tutorId ? { ...x, text: x.text + delta } : x)));
          speaker?.feed(delta);
        },
        onDone: async (d) => {
          setTurns((t) => t.map((x) => (x.id === tutorId ? { ...x, streaming: false, phase: d.phase } : x)));
          setPhase(d.phase);
          setTargetNode(d.target_node);
          streamDoneRef.current = true;
          speaker?.flush();
          if (!speaker?.supported) setVoice("idle");
          else maybeIdle();
          await refreshMastery(sessionId);
        },
        onError: async (m) => {
          setError(m);
          streamDoneRef.current = true;
          setVoice("idle");
          // The grade may have landed before the tutor call failed - show it.
          await refreshMastery(sessionId).catch(() => {});
        },
      });
      if (!started) {
        streamDoneRef.current = true;
        setVoice("idle");
      }
    },
    [sessionId, phase, refreshMastery, maybeIdle],
  );

  const startListening = useCallback(() => {
    const listener = listenerRef.current;
    if (!listener?.supported) return;
    speakerRef.current?.cancel();
    setVoice("listening");
    listener.start(
      (t) => setInterim(t),
      (finalText) => {
        if (finalText) void submit(finalText);
        else setVoice("idle");
      },
      () => setInterim(""),
    );
  }, [submit]);

  const stopListening = useCallback(() => listenerRef.current?.stop(), []);

  const chooseVoice = useCallback((v: string) => {
    setTtsVoice(v);
    const sp = speakerRef.current;
    if (sp instanceof ServerSpeaker) sp.voice = v || null;
    try {
      localStorage.setItem("tts.voice", v);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const targetTitle = useMemo(
    () => mastery.find((m) => m.node_id === targetNode)?.title ?? null,
    [mastery, targetNode],
  );

  if (!sessionId) {
    return (
      <main className="flex-1 flex flex-col items-center justify-center gap-8 px-6 text-center">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] text-zinc-500">CA Final · Financial Reporting</div>
          <h1 className="mt-3 text-4xl md:text-5xl font-semibold tracking-tight">Ind AS 115</h1>
          <p className="mt-3 text-zinc-400 max-w-md">
            Tell the tutor what you know. It maps your words to the syllabus, teaches only what is missing, and
            records mastery as you explain it back.
          </p>
        </div>
        <button
          onClick={begin}
          disabled={starting}
          className="rounded-full bg-zinc-100 text-black px-10 py-4 text-lg font-medium hover:scale-105 active:scale-95 transition disabled:opacity-50"
        >
          {starting ? "Connecting…" : "Begin session"}
        </button>
        {error && <p className="text-rose-300 text-sm max-w-md">{error}</p>}
      </main>
    );
  }

  return (
    <main className="flex-1 min-h-0 grid grid-rows-[auto_minmax(0,1fr)_auto_minmax(0,38vh)] md:grid-cols-[minmax(0,1fr)_360px] md:grid-rows-[auto_minmax(0,1fr)_auto] gap-x-6 px-4 md:px-6 py-4">
      {/* header */}
      <header className="md:col-span-2 flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <span className="uppercase tracking-[0.25em] text-zinc-500">Ind AS 115</span>
          <span className="rounded-full border border-zinc-700 px-2 py-0.5 text-zinc-300">{PHASE_LABEL[phase]}</span>
          {targetTitle && <span className="text-zinc-500 hidden sm:inline">→ {targetTitle}</span>}
        </div>
        <span className="flex items-center gap-2 text-zinc-600 tabular-nums">
          {ttsVoices.length > 0 ? (
            <label className="hidden sm:flex items-center gap-1">
              <span>{ttsLabel}</span>
              <select
                value={ttsVoice}
                onChange={(e) => chooseVoice(e.target.value)}
                aria-label="Tutor voice"
                className="bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5 text-zinc-300 focus:outline-none focus:border-zinc-600"
              >
                {ttsVoices.map((v) => (
                  <option key={v} value={v}>
                    {v.replace(/^en_(GB|US)-/, "$1 · ").replace(/-(medium|high|low|x_low)$/, "")}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <span className="hidden sm:inline">{ttsLabel}</span>
          )}
          <span>session {sessionId}</span>
        </span>
      </header>

      {/* transcript */}
      <section className="min-h-0 flex flex-col py-4">
        <Transcript turns={turns} interim={interim} />
      </section>

      {/* ledger (right rail on desktop, below on phone) */}
      <section className="min-h-0 md:row-span-2 py-2 md:py-4 order-last md:order-none border-t border-zinc-800/80 md:border-0">
        <MasteryGrid mastery={mastery} targetNode={targetNode} summary={summary} />
      </section>

      {/* voice controls */}
      <footer className="flex flex-col items-center gap-3 pb-2">
        <Waveform state={voice} />
        <TalkButton state={voice} sttSupported={sttSupported} onStart={startListening} onStop={stopListening} />
        <form
          className="flex w-full max-w-xl gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const t = typed.trim();
            if (t && voice === "idle") {
              setTyped("");
              void submit(t);
            }
          }}
        >
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={sttSupported ? "…or type your answer" : "Type your answer"}
            disabled={voice !== "idle"}
            className="flex-1 rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={voice !== "idle" || !typed.trim()}
            className="rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700 disabled:opacity-40"
          >
            Send
          </button>
        </form>
        {error && <p className="text-rose-300 text-xs">{error}</p>}
      </footer>
    </main>
  );
}
