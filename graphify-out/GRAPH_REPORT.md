# Graph Report - .  (2026-05-29)

## Corpus Check
- Corpus is ~6,363 words - fits in a single context window. You may not need a graph.

## Summary
- 125 nodes · 147 edges · 16 communities (11 shown, 5 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_TypeScript Config|TypeScript Config]]
- [[_COMMUNITY_Frontend Dependencies|Frontend Dependencies]]
- [[_COMMUNITY_FastAPI Endpoints|FastAPI Endpoints]]
- [[_COMMUNITY_Architecture Concepts|Architecture Concepts]]
- [[_COMMUNITY_Task Routing (Supervisor)|Task Routing (Supervisor)]]
- [[_COMMUNITY_Context Injection|Context Injection]]
- [[_COMMUNITY_Token Panel UI|Token Panel UI]]
- [[_COMMUNITY_Agent Card UI|Agent Card UI]]
- [[_COMMUNITY_Dashboard Page|Dashboard Page]]
- [[_COMMUNITY_Task Input UI|Task Input UI]]
- [[_COMMUNITY_Status Bar UI|Status Bar UI]]
- [[_COMMUNITY_App Layout|App Layout]]
- [[_COMMUNITY_Next.js Config|Next.js Config]]
- [[_COMMUNITY_PostCSS Config|PostCSS Config]]
- [[_COMMUNITY_Start Script|Start Script]]

## God Nodes (most connected - your core abstractions)
1. `compilerOptions` - 16 edges
2. `run_task()` - 8 edges
3. `get_context()` - 6 edges
4. `AI Dashboard Control` - 5 edges
5. `_run_task_bg()` - 4 edges
6. `classify_task()` - 4 edges
7. `scripts` - 4 edges
8. `Run` - 4 edges
9. `Supervisor — Task Router` - 4 edges
10. `TaskResponse` - 3 edges

## Surprising Connections (you probably didn't know these)
- `AI Dashboard Control — Tier 3 POC Brief` --conceptually_related_to--> `AI Dashboard Control`  [INFERRED]
  CLAUDE.md → README.md
- `Next.js Agent Rules (breaking changes warning)` --conceptually_related_to--> `Next.js Dashboard`  [INFERRED]
  dashboard/AGENTS.md → README.md

## Communities (16 total, 5 thin omitted)

### Community 0 - "TypeScript Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 1 - "Frontend Dependencies"
Cohesion: 0.11
Nodes (18): dependencies, next, react, react-dom, devDependencies, tailwindcss, @tailwindcss/postcss, @types/node (+10 more)

### Community 2 - "FastAPI Endpoints"
Cohesion: 0.17
Nodes (7): _broadcast(), Run supervisor.run_task in a thread and push trace events to WS clients., _run_task_bg(), submit_task(), TaskRequest, TaskResponse, BaseModel

### Community 3 - "Architecture Concepts"
Cohesion: 0.22
Nodes (10): Next.js Agent Rules (breaking changes warning), Context Loader, Next.js Dashboard, Ollama Local LLM, OpenRouter Cloud Routing, AI Dashboard Control, FastAPI Server, Supervisor — Task Router (+2 more)

### Community 4 - "Task Routing (Supervisor)"
Cohesion: 0.42
Nodes (8): classify_task(), main(), _ollama_chat(), _openrouter_chat(), _record_stats(), run_task(), RunTrace, show_stats()

### Community 5 - "Context Injection"
Cohesion: 0.33
Nodes (8): get_context(), _keywords(), _query_graphify(), context_loader.py ================= Loads relevant context from:   1. Obsidian v, Return a markdown context block to inject into the supervisor system message., Return (hit_count, path) sorted by relevance.      Longer / more specific keywor, _read_file(), _search_obsidian()

### Community 6 - "Token Panel UI"
Cohesion: 0.32
Nodes (5): PROVIDER_COLOR, fetchStats(), RunTrace, Stats, WS_BASE

### Community 7 - "Agent Card UI"
Cohesion: 0.29
Nodes (5): Props, PROVIDER_COLOR, TASK_ICON, subscribeToRun(), TraceEvent

### Community 8 - "Dashboard Page"
Cohesion: 0.33
Nodes (4): FALLBACK, ROSTER, fetchRun(), fetchRuns()

### Community 9 - "Task Input UI"
Cohesion: 0.33
Nodes (4): Props, TASK_TYPES, Run, submitTask()

## Knowledge Gaps
- **52 isolated node(s):** `start.sh script`, `config`, `name`, `version`, `private` (+47 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `Run supervisor.run_task in a thread and push trace events to WS clients.`, `context_loader.py ================= Loads relevant context from:   1. Obsidian v`, `Return (hit_count, path) sorted by relevance.      Longer / more specific keywor` to the rest of the system?**
  _56 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `TypeScript Config` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._
- **Should `Frontend Dependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.10526315789473684 - nodes in this community are weakly interconnected._