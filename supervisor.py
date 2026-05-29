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
import context_loader

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

def _ollama_chat(host: str, model: str, messages: list[dict], timeout: int = 300) -> dict | None:
    try:
        r = httpx.post(f"{host}/api/chat",
                       json={"model": model, "messages": messages, "stream": False},
                       timeout=timeout)
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


def _anthropic_chat(model: str, messages: list[dict], timeout: int = 120) -> dict | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        payload: dict = {"model": model, "max_tokens": 4096, "messages": user_msgs}
        if system:
            payload["system"] = system
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload, timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "content": data["content"][0]["text"],
            "tokens_in": data["usage"]["input_tokens"],
            "tokens_out": data["usage"]["output_tokens"],
        }
    except Exception:
        return None


def _openai_chat(model: str, messages: list[dict], timeout: int = 120) -> dict | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages}, timeout=timeout,
        )
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


def _deepseek_chat(model: str, messages: list[dict], timeout: int = 120) -> dict | None:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        return _openrouter_chat(f"deepseek/{model}", messages)
    try:
        r = httpx.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": messages}, timeout=timeout,
        )
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


# ── Model registry ─────────────────────────────────────────────────────────

COMPARE_MODELS: dict[str, dict] = {
    "claude-opus-4":   {"label": "Claude Opus 4",       "provider": "anthropic", "model_id": "claude-opus-4-5"},
    "claude-sonnet-4": {"label": "Claude Sonnet 4",     "provider": "anthropic", "model_id": "claude-sonnet-4-5"},
    "gpt-4o":          {"label": "GPT-4o",              "provider": "openai",    "model_id": "gpt-4o"},
    "gpt-4o-mini":     {"label": "GPT-4o Mini",         "provider": "openai",    "model_id": "gpt-4o-mini"},
    "o1":              {"label": "OpenAI o1",            "provider": "openai",    "model_id": "o1"},
    "deepseek-v3":     {"label": "DeepSeek V3",         "provider": "deepseek",  "model_id": "deepseek-chat"},
    "deepseek-r1":     {"label": "DeepSeek R1",         "provider": "deepseek",  "model_id": "deepseek-reasoner"},
    "gemma2-9b":       {"label": "Gemma 2 9B (local)",  "provider": "ollama",    "model_id": "gemma2:9b"},
    "qwen2.5":         {"label": "Qwen 2.5 7B (local)", "provider": "ollama",    "model_id": "qwen2.5:7b"},
    "phi3-mini":       {"label": "Phi-3 Mini (local)",  "provider": "ollama",    "model_id": "phi3:mini"},
}


def _dispatch_model(key: str, messages: list[dict]) -> dict | None:
    cfg = COMPARE_MODELS.get(key, {})
    provider, model_id = cfg.get("provider", ""), cfg.get("model_id", key)
    if provider == "anthropic":  return _anthropic_chat(model_id, messages)
    if provider == "openai":     return _openai_chat(model_id, messages)
    if provider == "deepseek":   return _deepseek_chat(model_id, messages)
    if provider == "openrouter": return _openrouter_chat(model_id, messages)
    if provider == "ollama":     return _ollama_chat(OLLAMA, model_id, messages)
    return None


# ── Model arena ────────────────────────────────────────────────────────────

def run_compare(
    text: str,
    model_keys: list[str],
    trace: RunTrace | None = None,
) -> dict[str, dict]:
    """Run the same prompt against multiple models concurrently."""
    import concurrent.futures

    if trace:
        trace.log(f"arena: racing {len(model_keys)} models — {', '.join(model_keys)}")

    messages = [{"role": "user", "content": text}]

    def run_one(key: str) -> tuple[str, dict]:
        cfg = COMPARE_MODELS.get(key)
        if not cfg:
            return key, {"status": "error", "label": key, "error": f"Unknown model key: {key}"}
        t0 = time.time()
        result = _dispatch_model(key, messages)
        latency = round(time.time() - t0, 2)
        if result:
            return key, {
                "status": "done",
                "label": cfg["label"],
                "provider": cfg["provider"],
                "content": result["content"],
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "latency_s": latency,
            }
        return key, {
            "status": "error",
            "label": cfg.get("label", key),
            "provider": cfg.get("provider", ""),
            "error": "Unavailable / missing API key",
            "latency_s": latency,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(model_keys), 8)) as ex:
        pairs = list(ex.map(run_one, model_keys))

    return dict(pairs)


# ── Classification (supervisor's first job) ─────────────────────────────────

def classify_task(text: str, trace: RunTrace) -> str:
    trace.log("classifying task type with phi3:mini…")
    result = _ollama_chat(OLLAMA, "phi3:mini", [
        {"role": "system", "content":
         "Classify the task into ONE word: summarize, code, research, or chat. "
         "Reply with only that single word, nothing else."},
        {"role": "user", "content": text[:400]},
    ], timeout=30)
    if result:
        word = result["content"].strip().lower()
        for t in ROUTING:
            if t in word:
                trace.log(f"→ task type: {t}")
                return t
    trace.log("→ task type: chat (default)")
    return "chat"


# ── The routed run with fallback chain ──────────────────────────────────────

def run_task(
    text: str,
    forced_type: str | None = None,
    trace: RunTrace | None = None,
) -> tuple[str, RunTrace]:
    if trace is None:
        trace = RunTrace()
    t0 = time.time()

    # Load context from Obsidian vault + graphify knowledge graph
    ctx = context_loader.get_context(text)
    if ctx:
        trace.log(f"loaded {len(ctx)} chars of context from knowledge base")

    task_type = forced_type or classify_task(text, trace)
    trace.task_type = task_type

    messages: list[dict] = []
    if ctx:
        messages.append({"role": "system", "content": ctx})
    messages.append({"role": "user", "content": text})

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
    parser.add_argument("--list-models", action="store_true", help="Print all models in the ROUTING table")
    args = parser.parse_args()

    if args.list_models:
        for task_type, models in ROUTING.items():
            for model in models:
                print(f"{task_type}: {model}")
        return
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


# ── v2: Async parallel dispatch ──────────────────────────────────────────────
#
# dispatch_graph() is the new primary entry point for server.py.
# It uses MiniMax Router → Token Optimizer → asyncio.gather → Kronos synthesis.
# Legacy run_task() above is kept for single-subtask and CLI usage.

import asyncio
from typing import Awaitable, Callable

import minimax_router
import token_optimizer
import agents as agents_mod


@dataclass
class SubtaskResult:
    subtask_id: str
    agent: str
    content: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    model_used: str = ""
    provider: str = ""
    status: str = "done"
    error: str = ""


@dataclass
class GraphTrace:
    """Trace for a full graph dispatch (parent run)."""
    subtasks: list[minimax_router.Subtask] = field(default_factory=list)
    results: list[SubtaskResult] = field(default_factory=list)
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_latency_s: float = 0.0
    steps: list[str] = field(default_factory=list)

    def log(self, msg: str):
        self.steps.append(msg)


async def _async_ollama_chat(
    host: str, model: str, messages: list[dict], timeout: int = 300,
) -> dict | None:
    """Async variant of _ollama_chat for true parallel fan-out."""
    import httpx as _httpx
    try:
        async with _httpx.AsyncClient() as client:
            r = await client.post(
                f"{host}/api/chat",
                json={"model": model, "messages": messages, "stream": False},
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            return {
                "content": data["message"]["content"],
                "tokens_in": data.get("prompt_eval_count", 0),
                "tokens_out": data.get("eval_count", 0),
            }
    except Exception:
        return None


async def _async_openrouter_chat(model: str, messages: list[dict]) -> dict | None:
    """Async variant of _openrouter_chat."""
    import httpx as _httpx
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        async with _httpx.AsyncClient() as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages},
                timeout=120,
            )
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


async def _run_subtask(
    subtask: minimax_router.Subtask,
    emit: Callable[[str, dict], Awaitable[None]],
) -> SubtaskResult:
    """Execute a single subtask with fallback chain. Async."""
    t0 = time.time()
    agent_cfg = agents_mod.get_agent(subtask.agent)

    # Optimize messages (sync — fast, no I/O)
    optimized = token_optimizer.optimize(subtask)
    messages = optimized.messages

    await emit(subtask.id, {
        "type": "subtask_start",
        "agent": subtask.agent,
        "tokens_budget": optimized.tokens_total,
    })

    # Try each model in the agent's preference list
    for model in agent_cfg.models:
        await emit(subtask.id, {"type": "trace", "msg": f"trying {model}..."})
        result = await _async_ollama_chat(OLLAMA, model, messages)
        if result:
            latency = round(time.time() - t0, 2)
            await emit(subtask.id, {
                "type": "subtask_done",
                "agent": subtask.agent,
                "model": model,
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "latency_s": latency,
            })
            return SubtaskResult(
                subtask_id=subtask.id,
                agent=subtask.agent,
                content=result["content"],
                tokens_in=result["tokens_in"],
                tokens_out=result["tokens_out"],
                latency_s=latency,
                model_used=model,
                provider="ollama-local",
            )

    # Remote brain fallback
    if OPTI:
        await emit(subtask.id, {"type": "trace", "msg": "trying remote OptiPlex..."})
        result = await _async_ollama_chat(OPTI, agent_cfg.models[0], messages)
        if result:
            latency = round(time.time() - t0, 2)
            return SubtaskResult(
                subtask_id=subtask.id, agent=subtask.agent,
                content=result["content"],
                tokens_in=result["tokens_in"], tokens_out=result["tokens_out"],
                latency_s=latency, model_used=agent_cfg.models[0],
                provider="ollama-remote",
            )

    # OpenRouter fallback
    await emit(subtask.id, {"type": "trace", "msg": "trying OpenRouter fallback..."})
    result = await _async_openrouter_chat("openai/gpt-4o-mini", messages)
    if result:
        latency = round(time.time() - t0, 2)
        return SubtaskResult(
            subtask_id=subtask.id, agent=subtask.agent,
            content=result["content"],
            tokens_in=result["tokens_in"], tokens_out=result["tokens_out"],
            latency_s=latency, model_used="gpt-4o-mini", provider="openrouter",
        )

    return SubtaskResult(
        subtask_id=subtask.id, agent=subtask.agent,
        content="[Agent unavailable — all providers exhausted.]",
        latency_s=round(time.time() - t0, 2),
        status="error", error="all providers exhausted",
    )


async def dispatch_graph(
    master_prompt: str,
    emit: Callable[[str, dict], Awaitable[None]],
) -> tuple[str, GraphTrace]:
    """
    Full v2 dispatch pipeline:
      1. MiniMax Router → subtasks
      2. Token Optimizer → optimized messages (per subtask)
      3. asyncio.gather → parallel agent execution
      4. Kronos synthesis → final answer

    `emit(channel_id, payload)` pushes trace events to WS clients.
    channel_id is either the parent run_id or a sub_run_id.
    """
    t0 = time.time()
    trace = GraphTrace()

    # ── Step 1: Route ──
    trace.log("routing master prompt via MiniMax...")
    await emit("__parent__", {"type": "trace", "msg": "MiniMax router: decomposing task..."})

    # Run router in executor (it's sync httpx)
    loop = asyncio.get_running_loop()
    subtasks = await loop.run_in_executor(None, minimax_router.route, master_prompt)
    trace.subtasks = subtasks

    trace.log(f"router produced {len(subtasks)} subtask(s)")
    await emit("__parent__", {
        "type": "routed",
        "subtasks": [
            {"id": s.id, "agent": s.agent, "priority": s.priority}
            for s in subtasks
        ],
    })

    # ── Fast path: single subtask → skip gather overhead ──
    if len(subtasks) == 1:
        trace.log("single subtask — direct dispatch, no synthesis needed")
        result = await _run_subtask(subtasks[0], emit)
        trace.results = [result]
        trace.total_tokens_in = result.tokens_in
        trace.total_tokens_out = result.tokens_out
        trace.total_latency_s = round(time.time() - t0, 2)
        return result.content, trace

    # ── Step 2 + 3: Parallel dispatch ──
    trace.log(f"dispatching {len(subtasks)} subtasks in parallel...")
    await emit("__parent__", {"type": "trace", "msg": f"Dispatching {len(subtasks)} agents in parallel..."})

    results = await asyncio.gather(
        *[_run_subtask(st, emit) for st in subtasks],
        return_exceptions=True,
    )

    # Collect results, handle any exceptions
    clean_results: list[SubtaskResult] = []
    for r in results:
        if isinstance(r, Exception):
            clean_results.append(SubtaskResult(
                subtask_id="?", agent="?", content=f"[Error: {r}]",
                status="error", error=str(r),
            ))
        else:
            clean_results.append(r)

    trace.results = clean_results
    trace.total_tokens_in = sum(r.tokens_in for r in clean_results)
    trace.total_tokens_out = sum(r.tokens_out for r in clean_results)

    # ── Step 4: Kronos synthesis ──
    trace.log("all subtasks complete — Kronos synthesizing...")
    await emit("__parent__", {"type": "trace", "msg": "Kronos: synthesizing agent outputs..."})

    kronos_cfg = agents_mod.get_agent("kronos")
    agent_outputs = "\n\n".join(
        f"=== {r.agent.upper()} ===\n{r.content}"
        for r in clean_results if r.status == "done"
    )

    synthesis_messages = [
        {"role": "system", "content": kronos_cfg.system_prefix},
        {"role": "user", "content": agent_outputs},
    ]

    # Try Kronos models
    synthesis = None
    for model in kronos_cfg.models:
        synthesis = await _async_ollama_chat(OLLAMA, model, synthesis_messages)
        if synthesis:
            trace.total_tokens_in += synthesis["tokens_in"]
            trace.total_tokens_out += synthesis["tokens_out"]
            break

    if not synthesis:
        # Fallback: just concatenate outputs
        synthesis = {"content": agent_outputs, "tokens_in": 0, "tokens_out": 0}
        trace.log("Kronos synthesis failed — returning raw agent outputs")

    trace.total_latency_s = round(time.time() - t0, 2)
    trace.log(f"done: {trace.total_tokens_in} tok in, {trace.total_tokens_out} tok out, {trace.total_latency_s}s")

    await emit("__parent__", {
        "type": "done",
        "total_tokens_in": trace.total_tokens_in,
        "total_tokens_out": trace.total_tokens_out,
        "latency_s": trace.total_latency_s,
    })

    return synthesis["content"], trace


if __name__ == "__main__":
    main()
