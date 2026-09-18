// Browser speech I/O for the MVP. Both halves are behind small interfaces so
// Deepgram (STT) and ElevenLabs (TTS) can replace them without touching page.tsx.
//
// Upgrade hooks: set NEXT_PUBLIC_DEEPGRAM_KEY / NEXT_PUBLIC_ELEVENLABS_KEY and
// implement DeepgramListener / ElevenLabsSpeaker against these interfaces.

/* eslint-disable @typescript-eslint/no-explicit-any */

export interface Listener {
  readonly supported: boolean;
  start(onInterim: (text: string) => void, onFinal: (text: string) => void, onEnd: () => void): void;
  stop(): void;
}

export interface Speaker {
  readonly supported: boolean;
  /** Feed streamed text; complete sentences are spoken as soon as they arrive. */
  feed(delta: string): void;
  /** Speak whatever is left after the stream ends. */
  flush(): void;
  cancel(): void;
  readonly onStateChange?: (speaking: boolean) => void;
}

// --------------------------------------------------------------------------- //
// STT: Web Speech API (Chrome). Continuous until stop() so a 60s monologue works.
// --------------------------------------------------------------------------- //
export class WebSpeechListener implements Listener {
  private rec: any = null;
  private finalText = "";
  readonly supported: boolean;

  constructor() {
    const w = typeof window !== "undefined" ? (window as any) : null;
    this.supported = !!(w && (w.SpeechRecognition || w.webkitSpeechRecognition));
  }

  start(onInterim: (t: string) => void, onFinal: (t: string) => void, onEnd: () => void) {
    const w = window as any;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    const rec = new Ctor();
    rec.lang = "en-IN";
    rec.continuous = true;
    rec.interimResults = true;
    this.finalText = "";
    rec.onresult = (e: any) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const chunk = e.results[i][0].transcript;
        if (e.results[i].isFinal) this.finalText += chunk + " ";
        else interim += chunk;
      }
      onInterim((this.finalText + interim).trim());
    };
    rec.onerror = () => {
      /* surfaced via onend with whatever we have */
    };
    rec.onend = () => {
      onFinal(this.finalText.trim());
      onEnd();
    };
    this.rec = rec;
    rec.start();
  }

  stop() {
    this.rec?.stop();
    this.rec = null;
  }
}

// --------------------------------------------------------------------------- //
// TTS: speechSynthesis with a sentence queue, so speech starts on the first
// full sentence rather than after the whole turn has streamed.
// --------------------------------------------------------------------------- //
export class WebSpeechSpeaker implements Speaker {
  private pending = "";
  private queue: string[] = [];
  private speaking = false;
  private current: SpeechSynthesisUtterance | null = null; // held so Chrome can't GC it mid-speech
  private watchdog: ReturnType<typeof setInterval> | null = null;
  readonly supported: boolean;
  readonly onStateChange?: (speaking: boolean) => void;

  constructor(onStateChange?: (speaking: boolean) => void) {
    this.supported = typeof window !== "undefined" && "speechSynthesis" in window;
    this.onStateChange = onStateChange;
  }

  feed(delta: string) {
    this.pending += delta;
    // Split on sentence enders followed by whitespace; keep the remainder.
    const re = /([^.!?]*[.!?]+)(\s+|$)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(this.pending)) !== null) {
      const sentence = m[1].trim();
      if (sentence) this.queue.push(sentence);
      last = re.lastIndex;
      if (m[2] === "") break; // ended at string end - may be mid-sentence, keep going next feed
    }
    this.pending = this.pending.slice(last);
    this.pump();
  }

  flush() {
    const rest = this.pending.trim();
    this.pending = "";
    if (rest) this.queue.push(rest);
    this.pump();
  }

  cancel() {
    this.queue = [];
    this.pending = "";
    this.stopWatchdog();
    this.current = null;
    if (this.supported) window.speechSynthesis.cancel();
    this.speaking = false;
    this.onStateChange?.(false);
  }

  private pump() {
    if (!this.supported || this.speaking) return;
    const next = this.queue.shift();
    if (!next) {
      this.onStateChange?.(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(next);
    u.rate = 1.0;
    u.pitch = 1.0;
    const voice = pickVoice();
    if (voice) u.voice = voice;
    const finish = () => {
      if (this.current !== u) return; // stale callback after cancel()
      this.stopWatchdog();
      this.current = null;
      this.speaking = false;
      this.pump();
    };
    u.onend = finish;
    u.onerror = finish;
    this.current = u;
    this.speaking = true;
    this.onStateChange?.(true);
    window.speechSynthesis.speak(u);
    this.startWatchdog(next.length, finish);
  }

  // Chrome sometimes never fires onend (embedded contexts, long utterances,
  // GC). Poll the engine: once it reports neither speaking nor pending after
  // speak() was issued - or a length-based hard cap elapses - treat it as done.
  private startWatchdog(chars: number, finish: () => void) {
    this.stopWatchdog();
    const started = Date.now();
    const hardCapMs = 1500 + chars * 90;
    let sawSpeaking = false;
    this.watchdog = setInterval(() => {
      const ss = window.speechSynthesis;
      if (ss.speaking) sawSpeaking = true;
      const elapsed = Date.now() - started;
      const idle = !ss.speaking && !ss.pending;
      if ((idle && (sawSpeaking || elapsed > 700)) || elapsed > hardCapMs) finish();
    }, 250);
  }

  private stopWatchdog() {
    if (this.watchdog) clearInterval(this.watchdog);
    this.watchdog = null;
  }
}

// --------------------------------------------------------------------------- //
// TTS: server-side engine (Piper / Kokoro) via POST /tts, one request per
// sentence. Synthesis of sentence N+1 overlaps playback of sentence N, so the
// first words start after one short synth and the rest pipelines behind it.
// --------------------------------------------------------------------------- //
export class ServerSpeaker implements Speaker {
  readonly supported = true;
  readonly onStateChange?: (speaking: boolean) => void;
  private pending = "";
  private queue: Array<{ text: string; started: boolean; audio: Promise<AudioBuffer | null> }> = [];
  private ctx: AudioContext | null = null;
  private current: AudioBufferSourceNode | null = null;
  private playing = false;
  private flushed = false;
  private inflight = 0;
  private abort = new AbortController();
  private static readonly PREFETCH = 2; // sentences synthesised ahead of playback
  /** Voice name understood by the server engine; null = server default. */
  voice: string | null = null;

  constructor(private readonly baseUrl: string, onStateChange?: (speaking: boolean) => void, voice: string | null = null) {
    this.onStateChange = onStateChange;
    this.voice = voice;
  }

  feed(delta: string) {
    this.flushed = false;
    this.pending += delta;
    const re = /([^.!?]*[.!?]+)(\s+|$)/g;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(this.pending)) !== null) {
      const sentence = m[1].trim();
      if (sentence) this.enqueue(sentence);
      last = re.lastIndex;
      if (m[2] === "") break;
    }
    this.pending = this.pending.slice(last);
    this.pump();
  }

  flush() {
    const rest = this.pending.trim();
    this.pending = "";
    if (rest) this.enqueue(rest);
    this.flushed = true;
    this.pump();
    this.settle();
  }

  cancel() {
    this.abort.abort();
    this.abort = new AbortController();
    this.queue = [];
    this.pending = "";
    this.inflight = 0;
    this.flushed = true;
    try {
      this.current?.stop();
    } catch {
      /* already stopped */
    }
    this.current = null;
    this.playing = false;
    this.onStateChange?.(false);
  }

  private enqueue(text: string) {
    // Lazily kick off synthesis only for the first PREFETCH items; later ones
    // start as earlier ones finish (see pump), which bounds server load.
    this.queue.push({ text, started: false, audio: Promise.resolve(null) });
    this.prefetch();
  }

  private prefetch() {
    for (const item of this.queue) {
      if (this.inflight >= ServerSpeaker.PREFETCH) break;
      if (item.started) continue;
      item.started = true;
      this.inflight++;
      item.audio = this.synth(item.text).finally(() => {
        this.inflight--;
        this.prefetch();
        this.pump();
      });
    }
  }

  private async synth(text: string): Promise<AudioBuffer | null> {
    try {
      const r = await fetch(`${this.baseUrl}/tts`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(this.voice ? { text, voice: this.voice } : { text }),
        signal: this.abort.signal,
      });
      if (!r.ok) return null;
      const bytes = await r.arrayBuffer();
      return await this.audioCtx().decodeAudioData(bytes);
    } catch {
      return null; // aborted or server error: skip this sentence rather than stall
    }
  }

  private audioCtx(): AudioContext {
    if (!this.ctx) this.ctx = new AudioContext();
    if (this.ctx.state === "suspended") void this.ctx.resume();
    return this.ctx;
  }

  private pump() {
    if (this.playing) return;
    const next = this.queue[0];
    if (!next || !next.started) {
      this.settle();
      return;
    }
    this.playing = true;
    this.onStateChange?.(true);
    void next.audio.then((buffer) => {
      this.queue.shift();
      if (!buffer) {
        this.playing = false;
        this.pump();
        return;
      }
      const ctx = this.audioCtx();
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      src.onended = () => {
        if (this.current === src) this.current = null;
        this.playing = false;
        this.pump();
      };
      this.current = src;
      src.start();
    });
  }

  private settle() {
    if (!this.playing && this.queue.length === 0 && this.inflight === 0 && this.flushed) {
      this.onStateChange?.(false);
    }
  }
}

export interface TTSInfo {
  engine: string;
  ready: boolean;
  voice?: string;
  voices?: string[];
}

/** Ask the tutor service which TTS engine it runs; falls back to the browser. */
export async function probeServerTTS(baseUrl: string): Promise<TTSInfo> {
  try {
    const r = await fetch(`${baseUrl}/tts/info`);
    if (!r.ok) return { engine: "browser", ready: false };
    return (await r.json()) as TTSInfo;
  } catch {
    return { engine: "browser", ready: false };
  }
}

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang === "en-IN") ??
    voices.find((v) => v.lang.startsWith("en-GB")) ??
    voices.find((v) => v.lang.startsWith("en")) ??
    null
  );
}
