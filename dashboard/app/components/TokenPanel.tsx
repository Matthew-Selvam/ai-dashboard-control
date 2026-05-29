"use client";

import { useEffect, useState } from "react";
import { fetchStats, Stats } from "../lib/api";

const PROVIDER_COLOR: Record<string, string> = {
  "ollama-local":  "var(--green)",
  "ollama-remote": "var(--blue)",
  "openrouter":    "var(--amber)",
};

export default function TokenPanel() {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    fetchStats().then(setStats).catch(() => {});
    const id = setInterval(() => fetchStats().then(setStats).catch(() => {}), 5000);
    return () => clearInterval(id);
  }, []);

  const loading = stats === null;
  const totals  = stats ? Object.entries(stats.totals) : [];
  const empty   = totals.length === 0;

  const totalRuns = totals.reduce((s, [, d]) => s + d.runs, 0);
  const totalIn   = totals.reduce((s, [, d]) => s + d.tokens_in, 0);
  const totalOut  = totals.reduce((s, [, d]) => s + d.tokens_out, 0);
  const localTok  = (stats?.totals["ollama-local"]?.tokens_in ?? 0)
                  + (stats?.totals["ollama-local"]?.tokens_out ?? 0);
  const localPct  = Math.round(localTok / Math.max(1, totalIn + totalOut) * 100);
  const maxTok    = Math.max(...totals.map(([, d]) => d.tokens_in + d.tokens_out), 1);

  return (
    <div className="glass" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Title */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="sidebar-label">Token Usage</div>
        {!empty && (
          <span style={{ fontSize: 10, color: "var(--dim)" }}>{totalRuns} runs</span>
        )}
      </div>

      {loading && (
        <div style={{ fontSize: 11, color: "var(--dimmer)" }}>Loading…</div>
      )}

      {!loading && empty && (
        <div style={{ fontSize: 11, color: "var(--dimmer)", lineHeight: 1.6 }}>
          No usage yet.<br />Submit a task to see stats.
        </div>
      )}

      {!empty && (
        <>
          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
            {[
              { label: "in",    val: totalIn.toLocaleString(),   color: "var(--fg)" },
              { label: "out",   val: totalOut.toLocaleString(),  color: "var(--fg)" },
              { label: "local", val: localPct + "%",             color: "var(--green)" },
            ].map(({ label, val, color }) => (
              <div key={label} style={{
                background: "var(--panel2)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "8px 6px",
                textAlign: "center",
              }}>
                <div style={{ fontSize: 14, fontWeight: 700, color, lineHeight: 1.1 }}>{val}</div>
                <div style={{ fontSize: 9, color: "var(--dimmer)", letterSpacing: "0.5px", textTransform: "uppercase", marginTop: 3 }}>{label}</div>
              </div>
            ))}
          </div>

          {/* Per-provider bars */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {totals.map(([prov, d]) => {
              const total = d.tokens_in + d.tokens_out;
              const color = PROVIDER_COLOR[prov] ?? "var(--dimmer)";
              const pct   = Math.round((total / maxTok) * 100);
              return (
                <div key={prov} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 11 }}>
                    <span style={{ color }}>{prov}</span>
                    <span style={{ color: "var(--dimmer)" }}>{d.runs} · {total.toLocaleString()} tok</span>
                  </div>
                  <div className="token-bar-track">
                    <div
                      className="token-bar-fill"
                      style={{ width: `${pct}%`, background: color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{
            fontSize: 10, color: "var(--dimmer)", lineHeight: 1.6,
            borderTop: "1px solid var(--border)", paddingTop: 10,
          }}>
            Local tokens cost $0.<br />Cloud only when local fails.
          </div>
        </>
      )}
    </div>
  );
}
