"use client";

import { useEffect, useState } from "react";
import { fetchHealth } from "../lib/api";

interface Health { status: string; ollama: string; remote: string | null; }

function Dot({ ok, pulse = true }: { ok: boolean; pulse?: boolean }) {
  return (
    <span
      className={ok && pulse ? "pulse-dot" : ""}
      style={{
        display: "inline-block",
        width: 7, height: 7,
        borderRadius: "50%",
        background: ok ? "var(--green)" : "var(--red)",
        boxShadow: ok ? "0 0 8px var(--green)" : "0 0 6px var(--red)",
        flexShrink: 0,
      }}
    />
  );
}

export default function StatusBar() {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => {});
    const id = setInterval(() => fetchHealth().then(setHealth).catch(() => {}), 8000);
    return () => clearInterval(id);
  }, []);

  const serverOk = health?.status === "ok";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", fontSize: 11, color: "var(--dim)" }}>
      {/* Supervisor status */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <Dot ok={serverOk} />
        <span style={{ color: serverOk ? "var(--dim)" : "var(--red)" }}>
          supervisor {serverOk ? "online" : "offline"}
        </span>
      </div>

      {serverOk && (
        <>
          {/* Ollama */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Dot ok={true} />
            <span style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {health?.ollama}
            </span>
          </div>

          {/* Remote brain */}
          {health?.remote ? (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Dot ok={true} />
              <span>remote: {health.remote}</span>
            </div>
          ) : (
            <span style={{ color: "var(--dimmer)" }}>no remote brain</span>
          )}
        </>
      )}
    </div>
  );
}
