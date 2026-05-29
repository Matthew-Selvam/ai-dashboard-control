"use client";

import { useRef, useState } from "react";
import { submitTask, Run } from "../lib/api";

const TASK_TYPES = ["auto", "code", "summarize", "research", "chat", "classify"];

interface Props {
  onSubmit: (run: Run) => void;
}

export default function TaskInput({ onSubmit }: Props) {
  const [prompt, setPrompt]     = useState("");
  const [taskType, setTaskType] = useState("auto");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const { run_id } = await submitTask(prompt.trim(), taskType === "auto" ? undefined : taskType);
      onSubmit({ run_id, status: "queued", prompt: prompt.trim(), steps: [] });
      setPrompt("");
      textRef.current?.focus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit");
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit(e as unknown as React.FormEvent);
    }
  }

  const canSubmit = !!prompt.trim() && !loading;

  return (
    <form onSubmit={handleSubmit} className="glass-bright" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "1.5px", textTransform: "uppercase", color: "var(--green)" }}>
          ⟩ Dispatch Task
        </span>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {TASK_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTaskType(t)}
              className={`chip${taskType === t ? " active" : ""}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Textarea */}
      <textarea
        ref={textRef}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Enter your task… (⌘↵ to send)"
        rows={3}
        disabled={loading}
        className="dark-input"
        style={{ resize: "none" }}
      />

      {/* Error */}
      {error && (
        <div style={{
          fontSize: 12, borderRadius: 6, padding: "8px 12px",
          background: "rgba(248,113,113,0.08)",
          border: "1px solid rgba(248,113,113,0.3)",
          color: "var(--red)",
        }}>
          ⚠ {error} — is the server running?{" "}
          <code style={{ fontSize: 11 }}>python server.py</code>
        </div>
      )}

      {/* Footer row */}
      <div style={{ display: "flex", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "var(--dimmer)" }}>
          {prompt.length > 0
            ? `${prompt.length} chars`
            : "supervisor → router → local-first fallback chain"}
        </span>
        <div style={{ flex: 1 }} />
        <button type="submit" disabled={!canSubmit} className="dispatch-btn">
          {loading ? "dispatching…" : "Dispatch ⟩"}
        </button>
      </div>
    </form>
  );
}
