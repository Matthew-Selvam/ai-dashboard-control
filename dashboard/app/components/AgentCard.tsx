"use client";

import { useEffect, useRef, useState } from "react";
import { Run, TraceEvent, subscribeToRun } from "../lib/api";

// ── Agent mascot map ───────────────────────────────────────────────────────────
// Mascot spec: kronos=⊕  cipher=⟨/⟩  scout=◎  vision=◈  quill=✦  atlas=∑  pulse=~

interface AgentInfo {
  icon:  string;
  label: string;
  color: string;
}

const AGENT_MASCOT: Record<string, AgentInfo> = {
  kronos: { icon: "⊕",   label: "Kronos", color: "#e63329" },
  cipher: { icon: "⟨/⟩", label: "Cipher", color: "#f97316" },
  scout:  { icon: "◎",   label: "Scout",  color: "#f97316" },
  vision: { icon: "◈",   label: "Vision", color: "#e63329" },
  quill:  { icon: "✦",   label: "Quill",  color: "#f97316" },
  atlas:  { icon: "∑",   label: "Atlas",  color: "#e63329" },
  pulse:  { icon: "~",   label: "Pulse",  color: "#f97316" },
};

// task_type returned by supervisor → agent responsible
const TASK_TO_AGENT: Record<string, string> = {
  code:      "cipher",
  summarize: "quill",
  research:  "scout",
  chat:      "quill",
  classify:  "kronos",
  data:      "atlas",
  vision:    "vision",
  monitor:   "pulse",
  // fallback: kronos as orchestrator
};

const DEFAULT_AGENT: AgentInfo = AGENT_MASCOT.kronos;

// ── Provider color ─────────────────────────────────────────────────────────────
const PROVIDER_COLOR: Record<string, string> = {
  "ollama-local":  "var(--green)",
  "ollama-remote": "var(--blue)",
  "openrouter":    "var(--amber)",
  "":              "var(--dimmer)",
};

interface Props {
  run: Run;
  onUpdate?: (run: Run) => void;
}

export default function AgentCard({ run, onUpdate }: Props) {
  const [live, setLive] = useState<Run>(run);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setLive(run);
    let cancelled = false;
    if (run.status === "queued" || run.status === "running") {
      wsRef.current?.close();
      subscribeToRun(run.run_id, (e: TraceEvent) => {
        setLive((prev) => {
          const next = { ...prev };
          if (e.type === "trace" && e.msg) {
            next.steps  = [...(prev.steps ?? []), e.msg];
            next.status = "running";
          } else if (e.type === "done") {
            next.status = "done";
            next.result = e.result;
            next.trace  = e.trace;
          } else if (e.type === "error") {
            next.status = "error";
            next.error  = e.error;
          }
          onUpdate?.(next);
          return next;
        });
      }).then((ws) => {
        if (cancelled) { ws.close(); return; }
        wsRef.current = ws;
      });
    }
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, [run.run_id, run.status, run.result]);  // eslint-disable-line react-hooks/exhaustive-deps

  const isRunning = live.status === "running";
  const isDone    = live.status === "done";
  const isError   = live.status === "error";

  const glowClass =
    isRunning ? "glow-amber" :
    isDone    ? "glow-done"  :
    isError   ? "glow-red"   : "";

  const badgeClass =
    live.status === "running" ? "badge badge-running" :
    live.status === "done"    ? "badge badge-done"    :
    live.status === "error"   ? "badge badge-error"   :
    "badge badge-queued";

  const provColor = PROVIDER_COLOR[live.trace?.provider ?? ""] ?? "var(--dimmer)";

  // Resolve agent from task_type
  const agentId  = TASK_TO_AGENT[live.trace?.task_type ?? ""] ?? "kronos";
  const agent    = AGENT_MASCOT[agentId] ?? DEFAULT_AGENT;

  return (
    <div className={`glass fade-up ${glowClass}`} style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>

        {/* Mascot icon + agent badge */}
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "3px 10px 3px 8px",
          borderRadius: 6,
          background: `${agent.color}14`,
          border: `1px solid ${agent.color}40`,
          flexShrink: 0,
        }}>
          <span style={{
            fontSize: 16,
            lineHeight: 1,
            color: agent.color,
            fontFamily: "inherit",
          }}>
            {agent.icon}
          </span>
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            color: agent.color,
            letterSpacing: "0.3px",
          }}>
            {agent.label}
          </span>
        </div>

        {/* Status badge */}
        <span className={badgeClass}>
          {isRunning && (
            <span className="pulse-dot" style={{
              display: "inline-block", width: 5, height: 5, borderRadius: "50%",
              background: "var(--amber)",
            }} />
          )}
          {live.status}
        </span>

        {/* Run ID */}
        <span style={{
          fontSize: 10, color: "var(--dimmer)", fontFamily: "inherit",
          background: "var(--panel2)", border: "1px solid var(--border)",
          borderRadius: 4, padding: "2px 6px", letterSpacing: "0.3px",
        }}>
          {live.run_id}
        </span>

        {/* Task type chip */}
        {live.trace?.task_type && (
          <span style={{
            fontSize: 10, fontWeight: 600, padding: "2px 8px",
            border: "1px solid var(--border2)", borderRadius: 4,
            color: "var(--dim)",
          }}>
            {live.trace.task_type}
          </span>
        )}

        <div style={{ flex: 1 }} />

        {/* Provider */}
        {live.trace?.model_used && (
          <span style={{
            fontSize: 10, padding: "2px 8px",
            border: `1px solid ${provColor}44`, borderRadius: 4,
            color: provColor,
          }}>
            {live.trace.model_used}
            <span style={{ color: "var(--dimmer)", margin: "0 4px" }}>·</span>
            {live.trace.provider}
          </span>
        )}
      </div>

      {/* ── Prompt ── */}
      <div style={{ fontSize: 12, color: "var(--dim)", lineHeight: 1.5 }}>
        <span style={{ color: agent.color, marginRight: 6 }}>›</span>
        {live.prompt.slice(0, 140)}{live.prompt.length > 140 ? "…" : ""}
      </div>

      {/* ── Live steps ── */}
      {(live.steps?.length ?? 0) > 0 && (
        <div style={{
          background: "var(--panel2)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 4,
          fontSize: 11,
          lineHeight: 1.5,
        }}>
          {live.steps!.map((s, i) => (
            <div key={i} style={{ color: "var(--dim)" }}>
              <span style={{ color: "var(--secondary)", marginRight: 4 }}>[supervisor]</span>{s}
            </div>
          ))}
          {isRunning && (
            <span className="cursor" style={{ color: "var(--amber)" }}>█</span>
          )}
        </div>
      )}

      {/* ── Result ── */}
      {live.result && (
        <div style={{
          borderRadius: 6,
          overflow: "hidden",
          border: "1px solid rgba(61,220,132,0.25)",
        }}>
          {/* Result header */}
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "6px 12px",
            background: "rgba(61,220,132,0.08)",
            borderBottom: "1px solid rgba(61,220,132,0.15)",
          }}>
            <span style={{
              fontSize: 9, fontWeight: 700, letterSpacing: "1.5px",
              textTransform: "uppercase", color: "var(--green)",
              display: "flex", alignItems: "center", gap: 6,
            }}>
              <span style={{ color: agent.color }}>{agent.icon}</span>
              Result
            </span>
            <button
              onClick={() => navigator.clipboard?.writeText(live.result!)}
              style={{
                fontSize: 9, letterSpacing: "1px", textTransform: "uppercase",
                color: "var(--dimmer)", background: "none", border: "none",
                cursor: "pointer", fontFamily: "inherit", padding: "2px 6px",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--fg)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--dimmer)")}
            >
              copy
            </button>
          </div>
          {/* Result body */}
          <div style={{
            padding: "14px 16px",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            background: "rgba(61,220,132,0.03)",
            color: "var(--fg)",
            lineHeight: 1.7,
            maxHeight: 480,
            overflowY: "auto",
          }}>
            {live.result}
          </div>
        </div>
      )}

      {/* ── Error ── */}
      {live.error && (
        <div style={{
          borderRadius: 6, padding: "8px 12px", fontSize: 12,
          background: "rgba(248,113,113,0.08)",
          border: "1px solid rgba(248,113,113,0.3)",
          color: "var(--red)",
        }}>
          ⚠ {live.error}
        </div>
      )}

      {/* ── Trace footer ── */}
      {live.trace && (
        <div style={{
          display: "flex", gap: 16, fontSize: 11, flexWrap: "wrap",
          color: "var(--dimmer)",
          borderTop: "1px solid var(--border)",
          paddingTop: 10,
        }}>
          <span>
            <span style={{ color: "var(--dim)" }}>↑</span> {live.trace.tokens_in.toLocaleString()}
            <span style={{ margin: "0 6px", color: "var(--border2)" }}>·</span>
            <span style={{ color: "var(--dim)" }}>↓</span> {live.trace.tokens_out.toLocaleString()}
            <span style={{ color: "var(--dimmer)", marginLeft: 3 }}>tok</span>
          </span>
          <span>{live.trace.latency_s}s</span>
          {live.trace.fallbacks_tried.length > 0 && (
            <span style={{ color: "var(--amber)" }}>
              fallbacks: {live.trace.fallbacks_tried.join(", ")}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
