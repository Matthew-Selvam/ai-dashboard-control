# AI Dashboard Control — v2 Architecture

> **Version**: 2.0 (2026-05-29)
> **Status**: Design → Scaffolding
> **Primary constraint**: Token efficiency — every prompt as short as possible.

---

## 1. System Overview

```
+---------------------------------------------------------------+
|  Tauri Desktop Shell  (src-tauri/ · Rust)                     |
|                                                               |
|   +-- Managed Sidecar: python server.py --port 8765           |
|   |     - lifecycle: spawn on launch, kill on quit             |
|   |     - health: poll /api/health every 5s                   |
|   |                                                           |
|   +-- WebView: Next.js dashboard                              |
|   |     - dev:  http://localhost:3000                          |
|   |     - prod: static export in dist/                        |
|   |                                                           |
|   +-- IPC Bridge (Tauri commands)                             |
|         - start_backend / stop_backend / backend_health       |
|         - TS detects Tauri vs browser, routes accordingly     |
+---------------------------------------------------------------+
          |  HTTP + WebSocket (localhost:8765)
          v
+---------------------------------------------------------------+
|  FastAPI Backend  (server.py)                                 |
|                                                               |
|   POST /api/task  ──> MiniMax Router ──> Task Graph           |
|                        (phi3:mini)        [{id, agent, ...}]  |
|                                                               |
|   For each subtask:                                           |
|     Token Optimizer ──> context_loader (scoped) ──> compress  |
|     ──> agent system prefix ──> dispatch to model             |
|                                                               |
|   asyncio.gather(subtask_1, subtask_2, ..., subtask_n)        |
|     - each gets own run_id + WS /ws/trace/{sub_run_id}       |
|     - parent run WS gets orchestration events                 |
|                                                               |
|   Kronos synthesis: waits for all, merges into final answer   |
+---------------------------------------------------------------+
          |  grep / file read
          v
+---------------------------------------------------------------+
|  Obsidian Vault  (~/Documents/ObsidianVault/CommandCenter)    |
|                                                               |
|   Per-agent folder routing:                                   |
|     cipher → 03-Code/, 04-Tech-Specs/                         |
|     scout  → 05-Research/, 00-Inbox/                          |
|     quill  → 06-Content/, 07-Brand/                           |
|     atlas  → 08-Data/, 09-Analytics/                          |
|     vision → 07-Brand/design/, 10-Design/                     |
|     pulse  → 11-Channels/, 12-Comms/                          |
|     kronos → (reads all, writes summaries to 02-Runs/)        |
+---------------------------------------------------------------+
```

---

## 2. Agent Roster

| Agent    | Icon | Role               | Color     | Models (local first)           | Obsidian Folders                  | Token Budget |
|----------|------|--------------------|-----------|--------------------------------|-----------------------------------|-------------|
| **kronos** | `+` | Orchestrator       | `#a78bfa` | gemma2:9b, qwen2.5:7b         | all (read), 02-Runs/ (write)      | 2000        |
| **cipher** | `{}` | Code              | `#60a5fa` | qwen2.5:7b, deepseek-coder:6.7b | 03-Code/, 04-Tech-Specs/        | 2000        |
| **scout**  | `>>` | Research          | `#4ade80` | gemma2:9b, phi3:mini           | 05-Research/, 00-Inbox/           | 2000        |
| **vision** | `()` | Images / Design   | `#f472b6` | llava:7b, bakllava             | 07-Brand/design/, 10-Design/      | 1500        |
| **quill**  | `""` | Writing           | `#fb923c` | gemma2:9b, qwen2.5:7b         | 06-Content/, 07-Brand/            | 2000        |
| **atlas**  | `#`  | Data / Analytics  | `#f59e0b` | qwen2.5:7b, gemma2:9b         | 08-Data/, 09-Analytics/           | 2000        |
| **pulse**  | `~`  | Comms             | `#38bdf8` | gemma2:9b, phi3:mini           | 11-Channels/, 12-Comms/           | 1800        |

**Design rule**: Every agent has a system prompt prefix (<=100 tokens) that establishes
its role, style, and constraints. This prefix is prepended by the Token Optimizer and
counts against the 2000-token budget.

---

## 3. MiniMax Router

**Replaces**: `supervisor.classify_task()` (single-label classifier)
**File**: `minimax_router.py`
**Model**: phi3:mini via local Ollama (~0.5s inference)

### Flow

```
Master Prompt (user input)
        |
        v
phi3:mini with routing system prompt
        |
        v
Parse JSON task graph
        |
  +-----+------+
  |      |      |
  v      v      v
Subtask  Subtask  Subtask
(cipher) (scout)  (quill)
```

### Contract

```python
@dataclass
class Subtask:
    id: str              # e.g. "sub_01"
    agent: str           # one of: kronos, cipher, scout, vision, quill, atlas, pulse
    prompt: str          # self-contained, max 200 words
    priority: int        # 1 = highest
    context_slice: str   # hint for context_loader: "brand guidelines", "auth code"
    depends_on: list[str] = field(default_factory=list)  # subtask ids this blocks on

def route(master_prompt: str) -> list[Subtask]:
    """Decompose into minimum required subtasks."""
```

### System Prompt for phi3:mini

The router model receives a tightly constrained system prompt (~150 tokens) that:
1. Lists the 7 agents and their one-line roles
2. Instructs: split into MINIMUM subtasks (bias toward fewer)
3. Each subtask prompt must be self-contained (no references to "the above")
4. Output strict JSON array — no markdown, no explanation
5. If the task is simple enough for one agent, return a single-item array

### Fallback

If phi3:mini returns unparseable JSON or is unavailable:
1. Regex-extract any JSON array from the response
2. If that fails: heuristic single-subtask routing (keyword match → best agent)
3. Last resort: route entire prompt to kronos as a single subtask

---

## 4. Token Optimizer

**File**: `token_optimizer.py`
**Goal**: No subtask ever exceeds 2000 tokens total input.

### Pipeline per Subtask

```
Subtask.prompt + Subtask.context_slice
        |
        v
context_loader.get_context(prompt, folders=agent_folders)
        |  returns raw context (may be 4000+ chars)
        v
compress(raw_context, budget=800 tokens)
        |  TF-IDF scoring against subtask.prompt
        |  keep only top-scoring sentences
        |  hard truncate at token budget
        v
agent_prefix (<=100 tokens) + compressed_context + subtask.prompt
        |
        v
Verify: total <= 2000 tokens
        |  if over: trim context first, then prompt tail
        v
Final messages[] ready for dispatch
```

### Token Counting

Dependency-free approximation: `len(text) / 4` (chars to tokens).
Good enough for budget enforcement. No tiktoken dependency.

### Compression Strategy

1. Split context into sentences
2. Score each sentence by keyword overlap with `subtask.prompt + subtask.context_slice`
3. Rank by score, take top-N until budget exhausted
4. Preserve document order (don't shuffle ranked sentences)

---

## 5. Obsidian Per-Agent Routing

**File**: `context_loader.py` (extended, backward compatible)

### Changes

```python
# New signature (old callers still work — folders=None means search all)
def get_context(task: str, folders: list[str] | None = None) -> str:

# _search_obsidian now accepts folder allowlist
def _search_obsidian(keywords: list[str], folders: list[str] | None = None) -> list[tuple[int, Path]]:
```

When `folders` is provided, grep is restricted to those subdirectories of `OBSIDIAN_ROOT`.
This means cipher only sees code/tech notes, quill only sees content/brand, etc.

### Folder Mapping

Defined once in `agents.py`, consumed by `token_optimizer.py` when calling
`context_loader.get_context(prompt, folders=agent.obsidian_folders)`.

---

## 6. Parallel Agent Dispatch

**Files**: `supervisor.py` (new `dispatch_graph` function), `server.py` (new endpoints)

### Supervisor Evolution

```python
# Legacy (kept for simple tasks / backward compat)
def run_task(text, forced_type=None, trace=None) -> tuple[str, RunTrace]:

# New: full graph dispatch
async def dispatch_graph(
    master_prompt: str,
    trace_emitter: Callable[[str, dict], Awaitable[None]],
) -> tuple[str, GraphTrace]:
    """
    1. MiniMax Router → subtasks
    2. Token Optimizer → optimized messages per subtask
    3. asyncio.gather → parallel agent execution
    4. Kronos synthesis → final answer
    """
```

### Execution Model

```
dispatch_graph("Build a landing page for the new product")
    |
    MiniMax Router → [
        {agent: "scout",  prompt: "Research competitor landing pages..."},
        {agent: "quill",  prompt: "Write hero copy for..."},
        {agent: "cipher", prompt: "Generate Next.js component for..."},
        {agent: "vision", prompt: "Describe ideal layout and color scheme..."},
    ]
    |
    Token Optimizer (runs on each in sequence — fast, no I/O)
    |
    asyncio.gather(
        run_subtask("scout",  messages_1, sub_run_id_1),
        run_subtask("quill",  messages_2, sub_run_id_2),
        run_subtask("cipher", messages_3, sub_run_id_3),
        run_subtask("vision", messages_4, sub_run_id_4),
    )
    |
    Kronos synthesis:
        system: "You are Kronos. Synthesize these agent outputs into a coherent response."
        user: [concatenated subtask outputs, each labeled by agent]
    |
    → Final answer
```

### Async Provider

New `async_ollama_chat` using `httpx.AsyncClient` for true parallel I/O.
The existing sync `_ollama_chat` stays for legacy `run_task`.

### WebSocket Channels

- `/ws/trace/{parent_run_id}` — orchestration events (router done, subtasks dispatched, synthesis started)
- `/ws/trace/{sub_run_id}` — per-subtask trace events (model chosen, tokens, latency)
- `/ws/dashboard` — all events (existing, unchanged)

---

## 7. Tauri Desktop Shell

**Directory**: `src-tauri/`

### Purpose

Wrap the web dashboard in a native desktop window. No Electron. Benefits:
- Native window management, system tray, global shortcuts
- Managed Python sidecar (no manual `start.sh`)
- Future: native file system access for Obsidian vault without grep subprocess

### Architecture

```
src-tauri/
  Cargo.toml          — tauri + serde + tokio dependencies
  tauri.conf.json      — window config, sidecar definition, permissions
  build.rs             — tauri build script
  src/
    main.rs            — app setup, sidecar lifecycle, IPC commands
    sidecar.rs         — spawn/kill python server.py, health checks
    ipc.rs             — Tauri command handlers
```

### IPC Commands

| Command           | Direction        | Purpose                              |
|-------------------|------------------|--------------------------------------|
| `start_backend`   | TS → Rust        | Spawn server.py sidecar              |
| `stop_backend`    | TS → Rust        | Kill sidecar process                 |
| `backend_health`  | TS → Rust → HTTP | Proxy /api/health, return status     |
| `get_backend_url` | TS → Rust        | Return sidecar port (for WS/HTTP)    |

### Frontend Bridge

`dashboard/app/lib/tauri.ts`:

```typescript
// Detects Tauri environment and provides backend URL
export const isTauri = () => typeof window !== "undefined" && "__TAURI__" in window;

export async function getBackendUrl(): Promise<string> {
    if (isTauri()) {
        const { invoke } = await import("@tauri-apps/api/core");
        return invoke<string>("get_backend_url");
    }
    return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";
}
```

`api.ts` updated to use `getBackendUrl()` instead of hardcoded `API` constant.

---

## 8. API Contract (v2)

### New / Changed Endpoints

| Method | Path                        | Change       | Notes                                    |
|--------|-----------------------------|-------------|------------------------------------------|
| POST   | `/api/task`                 | **changed** | Returns `{run_id, subtasks: [{sub_run_id, agent}]}` |
| GET    | `/api/task/{run_id}`        | **changed** | Includes `subtasks[]` with per-agent status |
| GET    | `/api/task/{run_id}/graph`  | **new**     | Returns the task graph from MiniMax router |
| GET    | `/api/agents`               | **new**     | Returns agent roster with status          |
| WS     | `/ws/trace/{run_id}`        | unchanged   | Works for both parent and sub run IDs     |

### Task Response Shape (v2)

```json
{
  "run_id": "a1b2c3d4",
  "status": "running",
  "prompt": "Build a landing page...",
  "subtasks": [
    {"sub_run_id": "s_01", "agent": "scout",  "status": "done",    "tokens_in": 480},
    {"sub_run_id": "s_02", "agent": "quill",  "status": "running", "tokens_in": 0},
    {"sub_run_id": "s_03", "agent": "cipher", "status": "running", "tokens_in": 0},
    {"sub_run_id": "s_04", "agent": "vision", "status": "queued",  "tokens_in": 0}
  ],
  "result": null,
  "trace": { ... }
}
```

---

## 9. File Structure (v2)

```
ai-dashboard-control/
  # ── Python backend ──
  server.py              # FastAPI + WS (evolved: graph dispatch, new endpoints)
  supervisor.py          # run_task (legacy) + dispatch_graph (new)
  context_loader.py      # get_context with folder routing
  agents.py              # NEW: agent roster, configs, system prompts
  minimax_router.py      # NEW: phi3:mini task decomposition
  token_optimizer.py     # NEW: per-subtask context compression
  requirements.txt       # fastapi, uvicorn, httpx

  # ── Tauri shell ──
  src-tauri/
    Cargo.toml
    tauri.conf.json
    build.rs
    src/
      main.rs
      sidecar.rs
      ipc.rs

  # ── Dashboard (Next.js + React) ──
  dashboard/
    app/
      page.tsx           # updated: task graph view, 7-agent roster
      layout.tsx
      globals.css
      lib/
        api.ts           # updated: graph types, dynamic backend URL
        agents.ts        # NEW: TS mirror of agents.py
        tauri.ts         # NEW: Tauri detection + IPC bridge
      components/
        AgentCard.tsx     # updated: subtask status per agent
        TaskInput.tsx
        TokenPanel.tsx
        StatusBar.tsx
        TaskGraph.tsx     # NEW: visual task graph (subtask DAG)
    package.json
    next.config.ts
    tsconfig.json

  # ── Scripts ──
  start.sh               # updated: Tauri-aware, fallback to manual
```

---

## 10. Token Budget Breakdown

For a typical 4-subtask dispatch:

```
Router call (phi3:mini):
  system prompt:  ~150 tokens
  user prompt:    ~100 tokens (master prompt, truncated)
  total:          ~250 tokens in, ~200 out

Per subtask (x4):
  agent prefix:   ~100 tokens
  compressed ctx: ~800 tokens (max)
  subtask prompt: ~400 tokens (max, from 200 words)
  total:          ~1300 tokens in, ~500 out

Kronos synthesis:
  system prompt:  ~100 tokens
  agent outputs:  ~2000 tokens (4 x 500)
  total:          ~2100 tokens in, ~800 out

Grand total: ~7750 tokens in, ~2800 tokens out
vs. v1 naive: ~6000+ tokens in single call with uncompressed context
```

The win: **parallel execution** (4x wall-clock speedup) with comparable token spend,
plus each agent gets *relevant* context instead of the full vault dump.

---

## 11. Migration Path

1. **Phase 1** (this session): Scaffold all new files. Keep v1 working via legacy `run_task`.
2. **Phase 2**: Wire MiniMax router → optimizer → parallel dispatch end-to-end.
3. **Phase 3**: Tauri wrapping + IPC bridge.
4. **Phase 4**: Dashboard UI for task graph visualization.

v1 `POST /api/task` continues to work — the new graph path activates when the
router returns >1 subtask. Single-subtask prompts take the fast legacy path.

---

## 12. Brand

- **Background**: `#0a0a0a`
- **Primary red**: `#e63329`
- **Accent orange**: `#f97316`
- **Agent colors**: see roster table above
- **Font**: system-ui, monospace for code/trace
- **Design language**: glass morphism panels, minimal borders, high contrast text
