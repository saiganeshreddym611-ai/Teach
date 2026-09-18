"use client";

import { useEffect, useRef } from "react";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

// Live mic waveform while listening (AnalyserNode); synthetic wave while the
// tutor speaks; a slow breathing line otherwise.
export default function Waveform({ state }: { state: VoiceState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function openMic() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const ctx = new AudioContext();
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        src.connect(analyser);
        analyserRef.current = analyser;
        streamRef.current = stream;
      } catch {
        analyserRef.current = null; // no mic permission: fall back to synthetic
      }
    }
    if (state === "listening") openMic();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      analyserRef.current = null;
    };
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let t = 0;
    const data = new Uint8Array(1024);

    const draw = () => {
      const { width, height } = canvas;
      ctx.clearRect(0, 0, width, height);
      ctx.lineWidth = 2;
      ctx.strokeStyle =
        state === "listening" ? "#34d399" : state === "speaking" ? "#60a5fa" : state === "thinking" ? "#fbbf24" : "#3f3f46";
      ctx.beginPath();
      const n = 256;
      const analyser = analyserRef.current;
      if (state === "listening" && analyser) analyser.getByteTimeDomainData(data);
      for (let i = 0; i < n; i++) {
        const x = (i / (n - 1)) * width;
        let y: number;
        if (state === "listening" && analyser) {
          const v = (data[Math.floor((i / n) * data.length)] - 128) / 128;
          y = height / 2 + v * height * 0.45;
        } else if (state === "speaking") {
          const env = Math.sin(t * 0.05 + i * 0.02) * 0.5 + 0.5;
          y = height / 2 + Math.sin(i * 0.15 + t * 0.2) * height * 0.3 * env;
        } else if (state === "thinking") {
          y = height / 2 + Math.sin(i * 0.3 + t * 0.15) * 4;
        } else {
          y = height / 2 + Math.sin(t * 0.03) * 2;
        }
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      t++;
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [state]);

  return <canvas ref={canvasRef} width={900} height={120} className="w-full h-24 md:h-32" aria-hidden />;
}
