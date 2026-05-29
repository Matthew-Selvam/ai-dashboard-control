#!/usr/bin/env python3
"""
AI-Dashboard-Control — FastAPI + WebSocket server
==================================================

Wraps supervisor.py and exposes:
  POST /api/task          — submit a task, get streaming trace via WS
  GET  /api/stats         — token usage report
  GET  /api/health        — liveness check
  WS   /ws/trace/{run_id} — live supervisor narration for a run

Usage:
  python server.py                 # starts on :8765
  python server.py --port 9000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import supervisor as sup

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="AI-Dashboard-Control", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Next.js dev server on any port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory run store { run_id: { status, trace, result } }
RUNS: dict[str, dict] = {}
# In-memory compare store { compare_id: { status, prompt, results } }
COMPARES: dict[str, dict] = {}
# Active WebSocket connections { run_id: [ws, ...] }
WS_CLIENTS: dict[str, list[WebSocket]] = {}


# ── Pydantic models ────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    prompt: str
    task_type: Optional[str] = None   # force type or let supervisor classify


class TaskResponse(BaseModel):
    run_id: str
    status: str = "queued"


class CompareRequest(BaseModel):
    prompt: str
    models: list[str] = ["claude-opus-4", "gpt-4o", "deepseek-v3"]


# ── Background task runner ────────────────────────────────────────────────────

async def _run_task_bg(run_id: str, prompt: str, task_type: Optional[str]):
    """Run supervisor.run_task in a thread and push trace events to WS clients."""
    RUNS[run_id]["status"] = "running"

    # Capture the running loop NOW (in async context) so the thread can use it safely.
    # asyncio.get_event_loop() inside a thread raises RuntimeError on Python 3.10+.
    loop = asyncio.get_running_loop()

    def patched_run(text, forced_type=None):
        # Capture context and store it on the run before delegating
        ctx = sup.context_loader.get_context(text)
        RUNS[run_id]["context"] = ctx

        trace = sup.RunTrace()
        original_log = trace.log

        def ws_log(msg):
            original_log(msg)
            loop.call_soon_threadsafe(
                loop.create_task,
                _broadcast(run_id, {"type": "trace", "msg": msg, "run_id": run_id})
            )

        trace.log = ws_log
        return sup.run_task(text, forced_type=forced_type, trace=trace)

    try:
        output, trace = await loop.run_in_executor(None, patched_run, prompt, task_type)
        RUNS[run_id]["status"] = "done"
        RUNS[run_id]["result"] = output
        RUNS[run_id]["trace"] = {
            "task_type": trace.task_type,
            "model_used": trace.model_used,
            "provider": trace.provider,
            "fallbacks_tried": trace.fallbacks_tried,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "latency_s": trace.latency_s,
            "steps": trace.steps,
        }
        await _broadcast(run_id, {
            "type": "done",
            "run_id": run_id,
            "result": output,
            "trace": RUNS[run_id]["trace"],
        })
    except Exception as e:
        RUNS[run_id]["status"] = "error"
        RUNS[run_id]["error"] = str(e)
        await _broadcast(run_id, {"type": "error", "run_id": run_id, "error": str(e)})


async def _broadcast(run_id: str, payload: dict):
    dead = []
    for ws in WS_CLIENTS.get(run_id, []):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        WS_CLIENTS[run_id].remove(ws)


# ── HTTP endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "ollama": sup.OLLAMA, "remote": sup.OPTI or None}


@app.post("/api/task", response_model=TaskResponse)
async def submit_task(req: TaskRequest):
    run_id = str(uuid.uuid4())[:8]
    RUNS[run_id] = {"status": "queued", "prompt": req.prompt, "result": None, "trace": None, "context": ""}
    asyncio.ensure_future(_run_task_bg(run_id, req.prompt, req.task_type))
    return TaskResponse(run_id=run_id)


@app.get("/api/task/{run_id}")
async def get_task(run_id: str):
    if run_id not in RUNS:
        return {"error": "not found"}
    return RUNS[run_id]


@app.get("/api/runs")
async def list_runs():
    return [
        {"run_id": k, "status": v["status"], "prompt": v.get("prompt", "")[:80]}
        for k, v in RUNS.items()
    ]


@app.get("/api/context/{run_id}")
async def get_context(run_id: str):
    if run_id not in RUNS:
        return {"error": "not found"}
    return {"run_id": run_id, "context": RUNS[run_id].get("context", "")}


@app.get("/api/stats")
async def stats():
    if not sup.STATS_FILE.exists():
        return {"runs": [], "totals": {}}
    return json.loads(sup.STATS_FILE.read_text())


@app.get("/api/models")
async def list_models():
    """Return available model registry for the arena."""
    return {
        k: {"label": v["label"], "provider": v["provider"]}
        for k, v in sup.COMPARE_MODELS.items()
    }


# ── Model arena endpoints ─────────────────────────────────────────────────────

async def _run_compare_bg(compare_id: str, prompt: str, model_keys: list[str]):
    loop = asyncio.get_running_loop()
    COMPARES[compare_id]["status"] = "running"
    try:
        results = await loop.run_in_executor(
            None, sup.run_compare, prompt, model_keys, None
        )
        COMPARES[compare_id]["status"] = "done"
        COMPARES[compare_id]["results"] = results
        await _broadcast(compare_id, {"type": "done", "compare_id": compare_id, "results": results})
    except Exception as e:
        COMPARES[compare_id]["status"] = "error"
        COMPARES[compare_id]["error"] = str(e)
        await _broadcast(compare_id, {"type": "error", "compare_id": compare_id, "error": str(e)})


@app.post("/api/compare")
async def submit_compare(req: CompareRequest):
    compare_id = str(uuid.uuid4())[:8]
    COMPARES[compare_id] = {
        "status": "queued", "prompt": req.prompt,
        "models": req.models, "results": {},
    }
    asyncio.ensure_future(_run_compare_bg(compare_id, req.prompt, req.models))
    return {"compare_id": compare_id, "status": "queued", "models": req.models}


@app.get("/api/compare/{compare_id}")
async def get_compare(compare_id: str):
    if compare_id not in COMPARES:
        return {"error": "not found"}
    return COMPARES[compare_id]


@app.get("/api/compares")
async def list_compares():
    return [
        {"compare_id": k, "status": v["status"], "prompt": v.get("prompt", "")[:80]}
        for k, v in COMPARES.items()
    ]


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/trace/{run_id}")
async def ws_trace(websocket: WebSocket, run_id: str):
    await websocket.accept()
    WS_CLIENTS.setdefault(run_id, []).append(websocket)
    # If run already done, send the final state immediately
    if run_id in RUNS and RUNS[run_id]["status"] == "done":
        await websocket.send_text(json.dumps({
            "type": "done", "run_id": run_id,
            "result": RUNS[run_id]["result"],
            "trace": RUNS[run_id]["trace"],
        }))
    try:
        while True:
            await websocket.receive_text()   # keep alive
    except WebSocketDisconnect:
        if run_id in WS_CLIENTS:
            WS_CLIENTS[run_id] = [ws for ws in WS_CLIENTS[run_id] if ws != websocket]


# General WS for dashboard-level events (all runs)
@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    await websocket.accept()
    WS_CLIENTS.setdefault("__dashboard__", []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if "__dashboard__" in WS_CLIENTS:
            WS_CLIENTS["__dashboard__"] = [
                ws for ws in WS_CLIENTS["__dashboard__"] if ws != websocket
            ]


# ── v2: Graph dispatch endpoints ─────────────────────────────────────────────

# Store for v2 graph runs { run_id: { status, prompt, subtasks, result, trace } }
GRAPH_RUNS: dict[str, dict] = {}


class GraphTaskRequest(BaseModel):
    prompt: str


async def _run_graph_bg(run_id: str, prompt: str):
    """Run supervisor.dispatch_graph and push events to WS clients."""
    GRAPH_RUNS[run_id]["status"] = "running"

    async def emit(channel: str, payload: dict):
        """Route events to the right WS channel."""
        resolved = run_id if channel == "__parent__" else channel
        payload["run_id"] = run_id
        await _broadcast(resolved, payload)
        # Also broadcast to the dashboard channel
        await _broadcast("__dashboard__", payload)

    try:
        output, trace = await sup.dispatch_graph(prompt, emit)
        GRAPH_RUNS[run_id]["status"] = "done"
        GRAPH_RUNS[run_id]["result"] = output
        GRAPH_RUNS[run_id]["trace"] = {
            "subtask_count": len(trace.subtasks),
            "subtasks": [
                {"id": s.id, "agent": s.agent, "priority": s.priority}
                for s in trace.subtasks
            ],
            "results": [
                {
                    "subtask_id": r.subtask_id, "agent": r.agent,
                    "status": r.status, "model_used": r.model_used,
                    "provider": r.provider,
                    "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
                    "latency_s": r.latency_s,
                }
                for r in trace.results
            ],
            "total_tokens_in": trace.total_tokens_in,
            "total_tokens_out": trace.total_tokens_out,
            "total_latency_s": trace.total_latency_s,
            "steps": trace.steps,
        }
        await _broadcast(run_id, {
            "type": "done", "run_id": run_id,
            "result": output,
            "trace": GRAPH_RUNS[run_id]["trace"],
        })
    except Exception as e:
        GRAPH_RUNS[run_id]["status"] = "error"
        GRAPH_RUNS[run_id]["error"] = str(e)
        await _broadcast(run_id, {"type": "error", "run_id": run_id, "error": str(e)})


@app.post("/api/task/graph")
async def submit_graph_task(req: GraphTaskRequest):
    """v2 endpoint: decomposes prompt via MiniMax Router, parallel agent fan-out."""
    run_id = str(uuid.uuid4())[:8]
    GRAPH_RUNS[run_id] = {
        "status": "queued", "prompt": req.prompt,
        "subtasks": [], "result": None, "trace": None,
    }
    asyncio.ensure_future(_run_graph_bg(run_id, req.prompt))
    return {"run_id": run_id, "status": "queued", "mode": "graph"}


@app.get("/api/task/graph/{run_id}")
async def get_graph_task(run_id: str):
    """Get status of a v2 graph run including per-subtask details."""
    if run_id not in GRAPH_RUNS:
        return {"error": "not found"}
    return GRAPH_RUNS[run_id]


@app.get("/api/agents")
async def list_agents():
    """Return the full agent roster for the dashboard sidebar."""
    return {
        name: {
            "icon": cfg.icon,
            "role": cfg.role,
            "color": cfg.color,
            "models": cfg.models,
            "token_budget": cfg.token_budget,
            "obsidian_folders": list(cfg.obsidian_folders),
        }
        for name, cfg in agents_mod.AGENTS.items()
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run("server:app", host=args.host, port=args.port, reload=True, log_level="info")
