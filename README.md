# AI Dashboard Control

A local AI orchestration dashboard that routes tasks to language models (Ollama local or OpenRouter cloud), tracks runs, and displays live stats in a Next.js UI.

## What it is

- **supervisor.py** — routes incoming tasks to the right model based on keyword rules, manages run lifecycle
- **server.py** — FastAPI backend exposing the supervisor over HTTP (`/api/runs`, `/api/dispatch`, etc.)
- **context_loader.py** — loads relevant context from local files for each run
- **dashboard/** — Next.js frontend showing live run status, token stats, and dispatch controls

## How to run

```bash
bash start.sh
```

This starts the supervisor server on `:8765` and the Next.js dashboard on `:3000`.

## Environment variables

| Variable | Description |
|---|---|
| `OLLAMA_HOST` | Base URL for the local Ollama instance (e.g. `http://localhost:11434`) |
| `OPENROUTER_API_KEY` | API key for OpenRouter cloud model routing |
| `OPTI_HOST` | Base URL for the Opti inference endpoint |
