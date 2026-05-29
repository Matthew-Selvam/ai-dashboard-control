// API client for the supervisor FastAPI backend

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";
const WS_BASE = API.replace(/^http/, "ws");

export interface TraceEvent {
  type: "trace" | "done" | "error";
  run_id: string;
  msg?: string;
  result?: string;
  error?: string;
  trace?: RunTrace;
}

export interface RunTrace {
  task_type: string;
  model_used: string;
  provider: string;
  fallbacks_tried: string[];
  tokens_in: number;
  tokens_out: number;
  latency_s: number;
  steps: string[];
}

export interface Run {
  run_id: string;
  status: "queued" | "running" | "done" | "error";
  prompt: string;
  result?: string;
  trace?: RunTrace;
  error?: string;
  // local-only
  steps?: string[];
}

export interface Stats {
  runs: unknown[];
  totals: Record<string, { tokens_in: number; tokens_out: number; runs: number }>;
}

// ── HTTP ──────────────────────────────────────────────────────────────────────

export async function submitTask(prompt: string, task_type?: string): Promise<{ run_id: string }> {
  const res = await fetch(`${API}/api/task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, task_type }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchRuns(): Promise<Run[]> {
  const res = await fetch(`${API}/api/runs`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchRun(run_id: string): Promise<Run | null> {
  try {
    const res = await fetch(`${API}/api/task/${run_id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return { run_id, ...data };
  } catch {
    return null;
  }
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API}/api/stats`, { cache: "no-store" });
  if (!res.ok) return { runs: [], totals: {} };
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string; ollama: string; remote: string | null }> {
  try {
    const res = await fetch(`${API}/api/health`, { cache: "no-store" });
    return res.json();
  } catch {
    return { status: "unreachable", ollama: "", remote: null };
  }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export function subscribeToRun(
  run_id: string,
  onEvent: (e: TraceEvent) => void,
  onClose?: () => void
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws/trace/${run_id}`);
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch { /* ignore parse errors */ }
  };
  ws.onclose = () => onClose?.();
  return ws;
}
