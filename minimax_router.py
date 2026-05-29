"""
minimax_router.py — MiniMax Router (replaces classify_task)
============================================================

Input:  master prompt string
Output: list[Subtask] — JSON task graph

Uses phi3:mini locally to decompose the prompt into the MINIMUM
required subtasks. Each subtask is self-contained (max 200 words)
and assigned to one of the named agents.

Fallback chain:
  1. Parse phi3:mini JSON response
  2. Regex-extract JSON array from malformed response
  3. Heuristic single-subtask routing (keyword match)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field

import httpx

import agents

OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "phi3:mini")
MAX_PROMPT_WORDS = 200


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class Subtask:
    id: str
    agent: str
    prompt: str
    priority: int = 1
    context_slice: str = ""
    depends_on: list[str] = field(default_factory=list)


# ── System prompt for the router model ──────────────────────────────────────

_ROUTER_SYSTEM = f"""You split a user task into the MINIMUM subtasks needed.

Available agents:
{agents.roster_summary()}

Rules:
1. Output a JSON array. No markdown, no explanation.
2. Each subtask has: id (str), agent (str), prompt (str), priority (int 1=highest), context_slice (str).
3. Each prompt is SELF-CONTAINED — no references to "the above" or other subtasks.
4. Each prompt is under {MAX_PROMPT_WORDS} words.
5. If the task needs only one agent, return a single-item array.
6. Bias toward FEWER subtasks. Never split what one agent can handle alone.
7. context_slice is a short hint (2-5 words) of what knowledge the agent needs.

Example output:
[{{"id":"s01","agent":"cipher","prompt":"Write a Python function that...","priority":1,"context_slice":"auth module code"}}]"""


# ── Router ──────────────────────────────────────────────────────────────────

def route(master_prompt: str) -> list[Subtask]:
    """Decompose master_prompt into minimum subtasks via phi3:mini."""
    # Truncate prompt for the router (it only needs the gist)
    truncated = master_prompt[:600]

    raw = _call_router_model(truncated)
    if raw:
        parsed = _parse_response(raw)
        if parsed:
            return parsed

    # All parsing failed — heuristic fallback
    return _heuristic_route(master_prompt)


def _call_router_model(prompt: str) -> str | None:
    """Call phi3:mini via Ollama for task decomposition."""
    try:
        r = httpx.post(
            f"{OLLAMA}/api/chat",
            json={
                "model": ROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,  # deterministic routing
                    "num_predict": 512,  # cap output tokens
                },
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception:
        return None


def _parse_response(raw: str) -> list[Subtask] | None:
    """Try to parse router output into Subtask list. Multiple strategies."""

    # Strategy 1: direct JSON parse
    try:
        data = json.loads(raw.strip())
        if isinstance(data, list):
            return _validate_subtasks(data)
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract JSON array from surrounding text
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return _validate_subtasks(data)
        except json.JSONDecodeError:
            pass

    return None


def _validate_subtasks(data: list[dict]) -> list[Subtask] | None:
    """Validate and convert raw dicts into Subtask objects."""
    valid_agents = set(agents.agent_names()) - {"kronos"}  # kronos is not routable
    subtasks = []

    for item in data:
        if not isinstance(item, dict):
            continue

        agent = str(item.get("agent", "")).lower().strip()
        prompt = str(item.get("prompt", "")).strip()

        if not agent or not prompt:
            continue
        if agent not in valid_agents:
            # Try fuzzy match
            agent = _fuzzy_agent(agent, valid_agents)
            if not agent:
                continue

        # Enforce word limit
        words = prompt.split()
        if len(words) > MAX_PROMPT_WORDS:
            prompt = " ".join(words[:MAX_PROMPT_WORDS])

        subtasks.append(Subtask(
            id=str(item.get("id", f"s_{uuid.uuid4().hex[:4]}")),
            agent=agent,
            prompt=prompt,
            priority=int(item.get("priority", 1)),
            context_slice=str(item.get("context_slice", "")),
            depends_on=list(item.get("depends_on", [])),
        ))

    return subtasks if subtasks else None


def _fuzzy_agent(name: str, valid: set[str]) -> str | None:
    """Try to match a misspelled agent name."""
    # Direct substring match
    for v in valid:
        if v in name or name in v:
            return v
    return None


# ── Heuristic fallback ──────────────────────────────────────────────────────

# Keywords that suggest a specific agent
_AGENT_KEYWORDS: dict[str, list[str]] = {
    "cipher": ["code", "function", "class", "debug", "fix", "implement", "refactor",
               "python", "javascript", "typescript", "api", "endpoint", "test"],
    "scout":  ["research", "find", "search", "compare", "analyze", "investigate",
               "what is", "how does", "summarize article", "look up"],
    "quill":  ["write", "draft", "edit", "copy", "blog", "email", "content",
               "rewrite", "proofread", "headline", "tagline"],
    "atlas":  ["data", "metrics", "dashboard", "chart", "sql", "query",
               "numbers", "statistics", "report", "csv", "analytics"],
    "vision": ["design", "layout", "mockup", "wireframe", "logo", "image",
               "ui", "ux", "color", "brand visual", "screenshot"],
    "pulse":  ["message", "slack", "email send", "notify", "channel",
               "outreach", "reply", "communicate", "announce"],
}


def _heuristic_route(prompt: str) -> list[Subtask]:
    """Keyword-based single-subtask routing when phi3:mini fails."""
    lower = prompt.lower()
    scores: dict[str, int] = {}

    for agent_name, keywords in _AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[agent_name] = score

    if scores:
        best = max(scores, key=scores.get)  # type: ignore[arg-type]
    else:
        best = "scout"  # default: treat unknown tasks as research

    return [Subtask(
        id=f"s_{uuid.uuid4().hex[:4]}",
        agent=best,
        prompt=prompt[:800],  # hard truncate for safety
        priority=1,
        context_slice="general",
    )]
