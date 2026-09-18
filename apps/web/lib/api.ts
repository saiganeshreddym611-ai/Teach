// Thin client for the tutor service. The /turn endpoint is SSE over POST, so we
// parse the stream by hand instead of using EventSource (which is GET-only).

export const API_BASE = process.env.NEXT_PUBLIC_TUTOR_API ?? "http://localhost:8000";

export type Phase = "DIAGNOSTIC" | "INSTRUCT" | "TEACH_BACK" | "COMPLETE";
export type NodeStatus = "NOT_MENTIONED" | "GAP" | "PARTIAL" | "VERIFIED";

export interface Turn {
  id: string;
  role: "student" | "tutor";
  text: string;
  phase: Phase;
  ts: string;
}

export interface MasteryEntry {
  node_id: string;
  title: string;
  level: 1 | 2 | 3;
  parent: string | null;
  status: NodeStatus;
  confidence: number | null;
}

export interface LedgerEvent {
  id: string;
  student_id: string;
  node_id: string;
  status: NodeStatus;
  confidence: number;
  evidence_turn_id: string;
  phase: Phase;
  ts: string;
}

export interface SessionView {
  session_id: string;
  student_id: string;
  topic_id: string;
  phase: Phase;
  target_node: string | null;
  student_level_summary: string;
  mastery: MasteryEntry[];
  turns: Turn[];
  ledger: LedgerEvent[];
}

export interface Verdict {
  node_id: string;
  status: NodeStatus;
  confidence: number;
  evidence: string;
}

export interface GradeEvent {
  verdicts: Verdict[];
  summary: string;
}

export interface DoneEvent {
  phase: Phase;
  target_node: string | null;
  tutor_turn_id: string;
  student_turn_id: string;
  ledger_delta: LedgerEvent[];
}

export async function createSession(studentId = "demo_student", topicId = "ind_as_115") {
  const r = await fetch(`${API_BASE}/session`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ student_id: studentId, topic_id: topicId }),
  });
  if (!r.ok) throw new Error(`createSession ${r.status}: ${await r.text()}`);
  return (await r.json()) as { session_id: string; phase: Phase; opening_prompt: string };
}

export async function getSession(sessionId: string): Promise<SessionView> {
  const r = await fetch(`${API_BASE}/session/${sessionId}`);
  if (!r.ok) throw new Error(`getSession ${r.status}`);
  return (await r.json()) as SessionView;
}

export interface TurnHandlers {
  onGrade?: (g: GradeEvent) => void;
  onText?: (delta: string) => void;
  onDone?: (d: DoneEvent) => void;
  onError?: (message: string) => void;
}

export async function streamTurn(sessionId: string, transcript: string, h: TurnHandlers): Promise<void> {
  const r = await fetch(`${API_BASE}/session/${sessionId}/turn`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ transcript }),
  });
  if (!r.ok || !r.body) {
    h.onError?.(`turn ${r.status}: ${await r.text()}`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      dispatch(block, h);
    }
  }
  if (buf.trim()) dispatch(buf, h);
}

function dispatch(block: string, h: TurnHandlers) {
  let kind = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) kind = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!kind) return;
  const payload = data ? JSON.parse(data) : {};
  switch (kind) {
    case "grade":
      h.onGrade?.(payload as GradeEvent);
      break;
    case "text":
      h.onText?.((payload as { delta: string }).delta);
      break;
    case "done":
      h.onDone?.(payload as DoneEvent);
      break;
    case "error":
      h.onError?.((payload as { message: string }).message);
      break;
  }
}
