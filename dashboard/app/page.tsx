"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchRun, fetchRuns, Run } from "./lib/api";
import { AGENTS, AGENT_ORDER } from "./lib/agents";
import AgentCard from "./components/AgentCard";
import TaskInput from "./components/TaskInput";
import TokenPanel from "./components/TokenPanel";
import StatusBar from "./components/StatusBar";
import ModelArena from "./components/ModelArena";

// Derive roster from the single source of truth (agents.ts).
// Override colors with brand palette: alternate red/orange per agent.
const BRAND_COLORS: Record<string, string> = {
  kronos: "#e63329", cipher: "#f97316", scout: "#f97316",
  vision: "#e63329", quill: "#f97316", atlas: "#e63329", pulse: "#f97316",
};
const ROSTER = AGENT_ORDER.map((id) => ({
  id,
  icon: AGENTS[id].icon,
  label: id.charAt(0).toUpperCase() + id.slice(1),
  role: AGENTS[id].role,
  color: BRAND_COLORS[id] ?? AGENTS[id].color,
}));

const FALLBACK = [
  { label: "local Ollama",    color: "var(--green)" },
  { label: "remote OptiPlex", color: "var(--blue)" },
  { label: "OpenRouter cloud",color: "var(--amber)" },
  { label: "heuristic save",  color: "var(--red)" },
];

type Tab = "tasks" | "arena";

export default function Dashboard() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [tab, setTab] = useState<Tab>("tasks");

  // Hydrate on mount, then poll every 4s to catch runs submitted elsewhere
  useEffect(() => {
    fetchRuns().then((runs) => {
      setRuns(runs);
      // Fetch full details for already-completed runs (stubs have no result)
      runs.forEach((r) => {
        if ((r.status === "done" || r.status === "error") && !r.result) {
          fetchRun(r.run_id).then((full) => {
            if (full) setRuns((prev) => prev.map((x) => x.run_id === full.run_id ? full : x));
          });
        }
      });
    });

    const id = setInterval(async () => {
      const fresh = await fetchRuns();
      setRuns((prev) => {
        const prevIds = new Set(prev.map((r) => r.run_id));
        const newRuns = fresh.filter((r) => !prevIds.has(r.run_id));
        if (newRuns.length === 0) return prev;

        // Fetch full details for completed runs, add stubs for in-progress
        for (const r of newRuns) {
          if (r.status === "done" || r.status === "error") {
            fetchRun(r.run_id).then((full) => {
              if (full) setRuns((p) => p.map((x) => x.run_id === full.run_id ? full : x));
            });
          }
        }
        return [...newRuns, ...prev];
      });
    }, 4000);

    return () => clearInterval(id);
  }, []);

  const handleNewRun = useCallback((run: Run) => {
    setRuns((prev) => [run, ...prev]);
  }, []);

  const handleUpdate = useCallback((updated: Run) => {
    setRuns((prev) => prev.map((r) => (r.run_id === updated.run_id ? updated : r)));
  }, []);

  const activeCount = runs.filter((r) => r.status === "running").length;
  const doneCount   = runs.filter((r) => r.status === "done").length;

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* ── Header ── */}
      <header style={{
        position: "sticky", top: 0, zIndex: 50,
        background: "rgba(7,8,10,0.95)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border)",
        padding: "0 24px",
        height: 64,
        display: "flex",
        alignItems: "center",
        gap: 20,
      }}>
        {/* Brand */}
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.3px", lineHeight: 1 }}>
            <span style={{ color: "var(--fg)" }}>ai</span>
            <span style={{ color: "var(--green)" }}>-</span>
            <span style={{ color: "var(--fg)" }}>dashboard</span>
            <span style={{ color: "var(--border2)", margin: "0 6px" }}>·</span>
            <span style={{ color: "var(--dimmer)", fontWeight: 400, fontSize: 12 }}>control plane</span>
          </div>
          <div style={{ fontSize: 10, color: "var(--dimmer)", letterSpacing: "0.5px" }}>
            local-first · supervisor routing · fallback chain
          </div>
        </div>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Run counters */}
        <div style={{ display: "flex", gap: 20, fontSize: 12 }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span style={{ color: "var(--amber)", fontWeight: 700, fontSize: 18, lineHeight: 1 }}>
              {activeCount}
            </span>
            <span style={{ color: "var(--dimmer)", fontSize: 9, letterSpacing: "1px", textTransform: "uppercase" }}>running</span>
          </div>
          <div style={{ width: 1, background: "var(--border)", margin: "4px 0" }} />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span style={{ color: "var(--green)", fontWeight: 700, fontSize: 18, lineHeight: 1 }}>
              {doneCount}
            </span>
            <span style={{ color: "var(--dimmer)", fontSize: 9, letterSpacing: "1px", textTransform: "uppercase" }}>done</span>
          </div>
          <div style={{ width: 1, background: "var(--border)", margin: "4px 0" }} />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span style={{ color: "var(--fg)", fontWeight: 700, fontSize: 18, lineHeight: 1 }}>
              {runs.length}
            </span>
            <span style={{ color: "var(--dimmer)", fontSize: 9, letterSpacing: "1px", textTransform: "uppercase" }}>total</span>
          </div>
        </div>

        <div style={{ width: 1, background: "var(--border)", margin: "8px 0" }} />

        {/* Tabs */}
        <div style={{ display: "flex", gap: 4 }}>
          {(["tasks", "arena"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? "var(--green)" : "var(--panel2)",
                color: tab === t ? "#fff" : "var(--dimmer)",
                border: `1px solid ${tab === t ? "var(--green)" : "var(--border2)"}`,
                borderRadius: 6, padding: "4px 14px",
                fontFamily: "inherit", fontSize: 11, fontWeight: 700,
                letterSpacing: 0.5, textTransform: "uppercase",
                cursor: "pointer", transition: "all 0.12s",
              }}
            >
              {t === "tasks" ? "Tasks" : "⚡ Arena"}
            </button>
          ))}
        </div>

        <div style={{ width: 1, background: "var(--border)", margin: "8px 0" }} />

        {/* Status bar */}
        <StatusBar />
      </header>

      {/* ── Body ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* ── Left sidebar: Roster ── */}
        <aside className="hidden lg:flex" style={{
          flexDirection: "column",
          width: 200,
          flexShrink: 0,
          borderRight: "1px solid var(--border)",
          padding: "20px 12px",
          gap: 8,
        }}>
          <div className="sidebar-label" style={{ marginBottom: 8, paddingLeft: 4 }}>Roster</div>
          {ROSTER.map((agent) => (
            <div key={agent.id} className="glass" style={{ padding: "10px 12px", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18, color: agent.color, lineHeight: 1 }}>{agent.icon}</span>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: agent.color, lineHeight: 1.2 }}>{agent.label}</div>
                <div style={{ fontSize: 10, color: "var(--dimmer)", marginTop: 2 }}>{agent.role}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop: "auto", fontSize: 10, color: "var(--dimmer)", lineHeight: 1.6, paddingLeft: 4 }}>
            Named agents v0.1<br />
            Prompt routing in v0.2
          </div>
        </aside>

        {/* ── Main canvas ── */}
        <main style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", padding: 20, gap: 16 }}>
          {tab === "tasks" ? (
            <>
              <TaskInput onSubmit={handleNewRun} />
              {runs.length === 0 ? (
                <div style={{
                  flex: 1, display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  gap: 12, textAlign: "center", color: "var(--dimmer)", padding: 60,
                }}>
                  <div style={{ fontSize: 48, color: "var(--border2)", lineHeight: 1 }}>◎</div>
                  <div style={{ fontSize: 14, color: "var(--dim)" }}>No tasks yet.</div>
                  <div style={{ fontSize: 12 }}>Submit a task above — the supervisor classifies, routes, and runs it.</div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {runs.map((run) => (
                    <AgentCard key={run.run_id} run={run} onUpdate={handleUpdate} />
                  ))}
                </div>
              )}
            </>
          ) : (
            <ModelArena />
          )}
        </main>

        {/* ── Right sidebar ── */}
        <aside className="hidden xl:flex" style={{
          flexDirection: "column",
          width: 260,
          flexShrink: 0,
          borderLeft: "1px solid var(--border)",
          padding: "20px 12px",
          gap: 12,
          overflowY: "auto",
        }}>
          <TokenPanel />

          {/* Fallback chain */}
          <div className="glass" style={{ padding: 14 }}>
            <div className="sidebar-label" style={{ marginBottom: 10 }}>Fallback Chain</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {FALLBACK.map((step, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                  <span style={{
                    width: 18, height: 18, borderRadius: "50%",
                    background: "var(--panel2)",
                    border: "1px solid var(--border2)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 9, color: "var(--dimmer)", flexShrink: 0,
                  }}>
                    {i + 1}
                  </span>
                  <span style={{ color: step.color }}>{step.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* How to run */}
          <div className="glass" style={{ padding: 14 }}>
            <div className="sidebar-label" style={{ marginBottom: 8 }}>How to run</div>
            <code style={{ fontSize: 11, color: "var(--green)", display: "block", marginBottom: 6 }}>
              python server.py
            </code>
            <div style={{ fontSize: 11, color: "var(--dimmer)", lineHeight: 1.6 }}>
              then open this page.<br />Ollama must be running.
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
