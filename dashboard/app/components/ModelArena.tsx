"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  submitCompare, fetchCompare, fetchModels,
  type CompareRun, type ModelResult, type ModelMeta,
} from "../lib/api";

// ── Provider colours (text) ────────────────────────────────────────────────
const PROVIDER_COLOR: Record<string, string> = {
  anthropic:  "var(--orange)",
  openai:     "var(--blue)",
  deepseek:   "var(--purple)",
  ollama:     "var(--cyan)",
  openrouter: "var(--amber)",
};

// ── Default model selection ────────────────────────────────────────────────
const DEFAULT_SELECTION = ["claude-opus-4", "gpt-4o", "deepseek-v3"];

// ── Single model column ────────────────────────────────────────────────────
function ModelColumn({
  modelKey,
  result,
  isRunning,
}: {
  modelKey: string;
  result?: ModelResult;
  isRunning: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const providerColor = result ? (PROVIDER_COLOR[result.provider] ?? "var(--dim)") : "var(--dim)";
  const label = result?.label ?? modelKey;

  const copy = () => {
    if (result?.content) {
      navigator.clipboard.writeText(result.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="glass" style={{
      flex: "1 1 280px", minWidth: 0, display: "flex", flexDirection: "column",
      overflow: "hidden",
    }}>
      {/* Column header */}
      <div style={{
        padding: "10px 14px", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
      }}>
        <div style={{
          width: 7, height: 7, borderRadius: "50%",
          background: result ? (result.status === "done" ? providerColor : "var(--red)") : "var(--border2)",
          flexShrink: 0,
        }} />
        <span style={{ fontWeight: 700, fontSize: 12, color: "var(--fg)", flex: 1 }}>
          {label}
        </span>
        {result && (
          <span style={{ fontSize: 10, color: providerColor, fontWeight: 600, letterSpacing: 0.5 }}>
            {result.provider?.toUpperCase()}
          </span>
        )}
      </div>

      {/* Meta bar */}
      {result?.status === "done" && (
        <div style={{
          padding: "5px 14px", borderBottom: "1px solid var(--border)",
          display: "flex", gap: 12, flexShrink: 0,
        }}>
          <span style={{ fontSize: 10, color: "var(--dim)" }}>
            ⏱ {result.latency_s}s
          </span>
          <span style={{ fontSize: 10, color: "var(--dim)" }}>
            ↑{result.tokens_in ?? 0} ↓{result.tokens_out ?? 0} tok
          </span>
          <button
            onClick={copy}
            style={{
              marginLeft: "auto", background: "none", border: "none",
              color: copied ? "var(--green)" : "var(--dimmer)", cursor: "pointer",
              fontSize: 10, fontFamily: "inherit", padding: 0,
            }}
          >
            {copied ? "✓ copied" : "copy"}
          </button>
        </div>
      )}

      {/* Body */}
      <div style={{
        flex: 1, overflowY: "auto", padding: "12px 14px",
        fontSize: 12, lineHeight: 1.65, color: "var(--fg)",
        whiteSpace: "pre-wrap", wordBreak: "break-word",
        minHeight: 200,
      }}>
        {!result && isRunning && (
          <div style={{ display: "flex", gap: 6, alignItems: "center", color: "var(--dimmer)" }}>
            <span className="pulse-dot" style={{
              width: 6, height: 6, borderRadius: "50%",
              background: "var(--amber)", display: "inline-block",
            }} />
            running…
          </div>
        )}
        {!result && !isRunning && (
          <span style={{ color: "var(--dimmer)" }}>awaiting prompt</span>
        )}
        {result?.status === "error" && (
          <span style={{ color: "var(--red)" }}>
            ✕ {result.error}
          </span>
        )}
        {result?.status === "done" && result.content}
      </div>
    </div>
  );
}

// ── Main Arena component ───────────────────────────────────────────────────
export default function ModelArena() {
  const [availableModels, setAvailableModels] = useState<Record<string, ModelMeta>>({});
  const [selected, setSelected] = useState<string[]>(DEFAULT_SELECTION);
  const [prompt, setPrompt] = useState("");
  const [run, setRun] = useState<CompareRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load model list on mount
  useEffect(() => {
    fetchModels().then(setAvailableModels);
  }, []);

  // Poll for results while running
  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPoll = useCallback((compare_id: string) => {
    stopPoll();
    pollRef.current = setInterval(async () => {
      const data = await fetchCompare(compare_id);
      if (data) {
        setRun(data);
        if (data.status === "done" || data.status === "error") stopPoll();
      }
    }, 1200);
  }, [stopPoll]);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const toggleModel = (key: string) => {
    setSelected(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const handleSubmit = async () => {
    if (!prompt.trim() || selected.length === 0 || loading) return;
    setLoading(true);
    setError("");
    setRun(null);
    try {
      const { compare_id } = await submitCompare(prompt.trim(), selected);
      setRun({ compare_id, status: "running", prompt: prompt.trim(), models: selected, results: {} });
      startPoll(compare_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const isRunning = run?.status === "running" || loading;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--dimmer)", letterSpacing: 2, textTransform: "uppercase" }}>
            Model Arena
          </div>
          <div style={{ fontSize: 10, color: "var(--dimmer)" }}>
            side-by-side comparison — run the same prompt across models
          </div>
        </div>
        {run?.status === "done" && (
          <div className="badge badge-done" style={{ marginLeft: "auto" }}>done</div>
        )}
        {isRunning && (
          <div className="badge badge-running" style={{ marginLeft: "auto" }}>running</div>
        )}
      </div>

      {/* Model selector chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {Object.entries(availableModels).map(([key, meta]) => (
          <button
            key={key}
            className={`chip${selected.includes(key) ? " active" : ""}`}
            onClick={() => toggleModel(key)}
          >
            {meta.label}
          </button>
        ))}
        {Object.keys(availableModels).length === 0 &&
          DEFAULT_SELECTION.map(k => (
            <button
              key={k}
              className={`chip${selected.includes(k) ? " active" : ""}`}
              onClick={() => toggleModel(k)}
            >
              {k}
            </button>
          ))
        }
      </div>

      {/* Prompt input */}
      <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
        <textarea
          className="dark-input"
          rows={2}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit(); }}
          placeholder="Enter a prompt to race across all selected models… (⌘↵ to run)"
          style={{ flex: 1, resize: "none" }}
        />
        <button
          className="dispatch-btn"
          disabled={isRunning || selected.length === 0 || !prompt.trim()}
          onClick={handleSubmit}
          style={{ flexShrink: 0, height: 52 }}
        >
          ⚡ Race
        </button>
      </div>

      {error && (
        <div style={{ color: "var(--red)", fontSize: 11 }}>✕ {error}</div>
      )}

      {selected.length === 0 && (
        <div style={{ color: "var(--dimmer)", fontSize: 11 }}>
          Select at least one model above to compare.
        </div>
      )}

      {/* Results grid */}
      {(run || isRunning) && selected.length > 0 && (
        <div style={{
          display: "flex", gap: 10, flex: 1, minHeight: 0,
          overflowX: "auto",
        }}>
          {selected.map(key => (
            <ModelColumn
              key={key}
              modelKey={key}
              result={run?.results?.[key]}
              isRunning={isRunning}
            />
          ))}
        </div>
      )}
    </div>
  );
}
