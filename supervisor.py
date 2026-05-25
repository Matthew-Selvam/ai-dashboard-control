#!/usr/bin/env python3
"""
AI-Dashboard-Control — Supervisor Router MVP
============================================

The "Jarvis"-grade control plane, CLI MVP. A small supervisor model routes each
task to the right model, with a provider fallback chain and token transparency.

Capabilities (MVP):
    - Task classification (phi3:mini, <1s)
    - Model routing per task type
    - Fallback chain: local Ollama → (remote OptiPlex) → OpenRouter → heuristic
    - Token usage tracking per task
    - Run trace (the supervisor narrates what it's doing)

Usage:
    python supervisor.py "summarize this article: <text>"
    python supervisor.py --task code "write a python function to reverse a list"
    python supervisor.py --stats          # show token usage report

Env: OLLAMA_HOST, OPENROUTER_API_KEY (optional fallback), OPTI_HOST (remote brain)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import httpx

OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OPTI = os.getenv("OPTI_HOST", "")          # remote P40 brain over Tailscale
STATS_FILE = Path.home() / ".ai-dashboard" / "token_stats.json"

# Task type → model preference (local-first)
ROUTING = {
    "classify":  ["phi3:mini"],
    "summarize": ["gemma2:9b", "qwen2.5:7b"],
    "code":      ["qwen2.5:7b", "gemma2:9b"],
    "research":  ["gemma2:9b"],
    "chat":      ["gemma2:9b", "phi3:mini"],
}


@dataclass
class RunTrace:
    task_type: str = ""
    model_used: str = ""
    provider: str = ""
    fallbacks_tried: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    steps: list[str] = field(default_factory=list)

    def log(self, msg: str):
        self.steps.append(msg)
        print(f"  [supervisor] {msg}")


# ── Provider calls with fallback ────────────────────────────────────────────

def _ollama_chat(host: str, model: str, messages: list[dict]) -> dict | None:
    try:
        r = httpx.post(f"{host}/api/chat",
                       json={"model": model, "messages": messages, "stream": False},
                       timeout=120)
        r.raise_for_status()
        data = r.json()
        return {
            "content": data["message"]["content"],
            "tokens_in": data.get("prompt_eval_count", 0),
            "tokens_out": data.get("eval_count", 0),
        }
    except Exception:
        return None


def _openrouter_chat(model: str, messages: list[dict]) -> dict | None:
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "messages": messages}, timeout=120)
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        return {
            "content": data["choices"][0]["message"]["content"],
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
        }
    except Exception:
        return None


# ── Classification (supervisor's first job) ─────────────────────────────────

def classify_task(text: str, trace: RunTrace) -> str:
    trace.log("classifying task type with phi3:mini…")
    result = _ollama_chat(OLLAMA, "phi3:mini", [
        {"role": "system", "content":
         "Classify the task into ONE word: classify, summarize, code, research, or chat. "
         "Reply with only the word."},
        {"role": "user", "content": text[:400]},
    ])
    if result:
        word = result["content"].strip().lower()
        for t in ROUTING:
            if t in word:
                trace.log(f"→ task type: {t}")
                return t
    trace.log("→ task type: chat (default)")
    return "chat"


# ── The routed run with fallback chain ──────────────────────────────────────

def run_task(text: str, forced_type: str | None = None) -> tuple[str, RunTrace]:
    trace = RunTrace()
    t0 = time.time()

    task_type = forced_type or classify_task(text, trace)
    trace.task_type = task_type

    messages = [{"role": "user", "content": text}]
    models = ROUTING.get(task_type, ["gemma2:9b"])

    # Fallback chain: local models → remote (OptiPlex) → OpenRouter
    for model in models:
        trace.log(f"trying local {model}…")
        result = _ollama_chat(OLLAMA, model, messages)
        if result:
            trace.model_used, trace.provider = model, "ollama-local"
            trace.tokens_in, trace.tokens_out = result["tokens_in"], result["tokens_out"]
            trace.latency_s = round(time.time() - t0, 2)
            _record_stats(trace)
            return result["content"], trace
        trace.fallbacks_tried.append(f"local/{model}")

    # Remote brain (OptiPlex P40)
    if OPTI:
        trace.log("local exhausted — trying remote OptiPlex brain…")
        result = _ollama_chat(OPTI, models[0], messages)
        if result:
            trace.model_used, trace.provider = models[0], "ollama-remote"
            trace.tokens_in, trace.tokens_out = result["tokens_in"], result["tokens_out"]
            trace.latency_s = round(time.time() - t0, 2)
            _record_stats(trace)
            return result["content"], trace
        trace.fallbacks_tried.append("remote/opti")

    # OpenRouter cloud fallback
    trace.log("trying OpenRouter cloud fallback…")
    result = _openrouter_chat("openai/gpt-4o-mini", messages)
    if result:
        trace.model_used, trace.provider = "gpt-4o-mini", "openrouter"
        trace.tokens_in, trace.tokens_out = result["tokens_in"], result["tokens_out"]
        trace.latency_s = round(time.time() - t0, 2)
        _record_stats(trace)
        return result["content"], trace
    trace.fallbacks_tried.append("openrouter")

    trace.log("ALL providers exhausted — returning heuristic response")
    trace.latency_s = round(time.time() - t0, 2)
    return "[All AI providers unavailable. Task saved for retry.]", trace


# ── Token stats ──────────────────────────────────────────────────────────────

def _record_stats(trace: RunTrace) -> None:
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    stats = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {"runs": [], "totals": {}}
    stats["runs"].append({
        "task_type": trace.task_type, "model": trace.model_used,
        "provider": trace.provider, "tokens_in": trace.tokens_in,
        "tokens_out": trace.tokens_out, "latency_s": trace.latency_s,
    })
    tot = stats["totals"]
    key = trace.provider or "unknown"
    tot.setdefault(key, {"tokens_in": 0, "tokens_out": 0, "runs": 0})
    tot[key]["tokens_in"] += trace.tokens_in
    tot[key]["tokens_out"] += trace.tokens_out
    tot[key]["runs"] += 1
    STATS_FILE.write_text(json.dumps(stats, indent=2))


def show_stats() -> None:
    if not STATS_FILE.exists():
        print("No token stats yet.")
        return
    stats = json.loads(STATS_FILE.read_text())
    print("📊 Token Usage by Provider\n")
    print(f"{'provider':<18} {'runs':<6} {'tokens_in':<12} {'tokens_out':<12}")
    print("-" * 50)
    for prov, d in stats["totals"].items():
        print(f"{prov:<18} {d['runs']:<6} {d['tokens_in']:<12} {d['tokens_out']:<12}")
    print(f"\nTotal runs: {len(stats['runs'])}  (local = $0 — cloud only when local fails)")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-Dashboard-Control supervisor")
    parser.add_argument("prompt", nargs="?", help="The task/prompt")
    parser.add_argument("--task", help="Force task type", choices=list(ROUTING.keys()))
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return
    if not args.prompt:
        print("Provide a prompt or --stats")
        return

    print(f"🧠 Supervisor processing task…\n")
    output, trace = run_task(args.prompt, args.task)
    print(f"\n{'─'*55}")
    print(f"Model: {trace.model_used} ({trace.provider}) · "
          f"{trace.tokens_in}→{trace.tokens_out} tok · {trace.latency_s}s")
    if trace.fallbacks_tried:
        print(f"Fallbacks tried: {', '.join(trace.fallbacks_tried)}")
    print(f"{'─'*55}\n")
    print(output)


if __name__ == "__main__":
    main()
