// API client for the supervisor FastAPI backend
// v2: supports both legacy single-task and graph dispatch modes

import { getBackendUrl, getWsUrl } from "./tauri";

// ── Lazy backend URL (resolved once, cached) ────────────────────────────────

let _apiCache: string | null = null;
let _wsCache: string | null = null;

async function api(): Promise<string> {
  if (!_apiCache) _apiCache = await getBackendUrl();
  return _apiCache;
}

async function wsBase(): Promise<string> {
  if (!_wsCache) _wsCache = await getWsUrl();
  return _wsCache;
}

// ── Types: Legacy (v1) ──────────────────────────────────────────────────────

export interface TraceEvent {
  type: "trace" | "done" | "error" | "routed" | "subtask_start" | "subtask_done";
  run_id: string;
  msg?: string;
  result?: string;
  error?: string;
  trace?: RunTrace;
  // v2 graph events
  subtasks?: { id: string; agent: string; priority: number }[];
  agent?: string;
  tokens_budget?: number;
  model?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_s?: number;
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

// ── Types: v2 Graph Dispatch ────────────────────────────────────────────────

export interface SubtaskInfo {
  id: string;
  agent: string;
  priority: number;
}

export interface SubtaskResult {
  subtask_id: string;
  agent: string;
  status: "done" | "error";
  model_used: string;
  provider: string;
  tokens_in: number;
  tokens_out: number;
  latency_s: number;
}

export interface GraphTrace {
  subtask_count: number;
  subtasks: SubtaskInfo[];
  results: SubtaskResult[];
  total_tokens_in: number;
  total_tokens_out: number;
  total_latency_s: number;
  steps: string[];
}

export interface GraphRun {
  run_id: string;
  status: "queued" | "running" | "done" | "error";
  prompt: string;
  subtasks: SubtaskInfo[];
  result?: string;
  trace?: GraphTrace;
  error?: string;
}

// ── Types: Compare / Arena ──────────────────────────────────────────────────

export interface ModelResult {
  status: "done" | "error";
  label: string;
  provider: string;
  content?: string;
  error?: string;
  tokens_in?: number;
  tokens_out?: number;
  latency_s?: number;
}

export interface CompareRun {
  compare_id: string;
  status: "queued" | "running" | "done" | "error";
  prompt: string;
  models: string[];
  results: Record<string, ModelResult>;
}

export interface ModelMeta {
  label: string;
  provider: string;
}

// ── HTTP: Legacy (v1) ───────────────────────────────────────────────────────

export async function submitTask(prompt: string, task_type?: string): Promise<{ run_id: string }> {
  const base = await api();
  const res = await fetch(`${base}/api/task`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, task_type }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchRuns(): Promise<Run[]> {
  const base = await api();
  const res = await fetch(`${base}/api/runs`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchRun(run_id: string): Promise<Run | null> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/task/${run_id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return { run_id, ...data };
  } catch {
    return null;
  }
}

export async function fetchStats(): Promise<Stats> {
  const base = await api();
  const res = await fetch(`${base}/api/stats`, { cache: "no-store" });
  if (!res.ok) return { runs: [], totals: {} };
  return res.json();
}

// ── HTTP: v2 Graph Dispatch ─────────────────────────────────────────────────

export async function submitGraphTask(prompt: string): Promise<{ run_id: string; mode: string }> {
  const base = await api();
  const res = await fetch(`${base}/api/task/graph`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchGraphRun(run_id: string): Promise<GraphRun | null> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/task/graph/${run_id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return { run_id, ...data };
  } catch {
    return null;
  }
}

export async function fetchAgents(): Promise<Record<string, {
  icon: string; role: string; color: string; models: string[];
  token_budget: number; obsidian_folders: string[];
}>> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/agents`, { cache: "no-store" });
    return res.ok ? res.json() : {};
  } catch {
    return {};
  }
}

// ── HTTP: Compare / Arena ───────────────────────────────────────────────────

export async function fetchModels(): Promise<Record<string, ModelMeta>> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/models`, { cache: "no-store" });
    return res.ok ? res.json() : {};
  } catch { return {}; }
}

export async function submitCompare(
  prompt: string,
  models: string[]
): Promise<{ compare_id: string }> {
  const base = await api();
  const res = await fetch(`${base}/api/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, models }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchCompare(compare_id: string): Promise<CompareRun | null> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/compare/${compare_id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.error) return null;
    return { compare_id, ...data };
  } catch { return null; }
}

export async function fetchHealth(): Promise<{ status: string; ollama: string; remote: string | null }> {
  try {
    const base = await api();
    const res = await fetch(`${base}/api/health`, { cache: "no-store" });
    return res.json();
  } catch {
    return { status: "unreachable", ollama: "", remote: null };
  }
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export async function subscribeToRun(
  run_id: string,
  onEvent: (e: TraceEvent) => void,
  onClose?: () => void
): Promise<WebSocket> {
  const base = await wsBase();
  const ws = new WebSocket(`${base}/ws/trace/${run_id}`);
  ws.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch { /* ignore parse errors */ }
  };
  ws.onclose = () => onClose?.();
  return ws;
}
