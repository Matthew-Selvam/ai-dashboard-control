"""
agents.py — Single source of truth for the agent roster.
============================================================

Every agent's config lives here: role, system prompt prefix,
Obsidian folders, model preferences, token budget.

Consumed by:
  - minimax_router.py  (agent names + roles for the routing prompt)
  - token_optimizer.py  (system prefix, obsidian_folders, token_budget)
  - supervisor.py       (model routing table)
  - dashboard agents.ts (mirrored manually — keep in sync)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentConfig:
    name: str
    icon: str
    role: str
    color: str
    system_prefix: str
    obsidian_folders: list[str]
    models: list[str]
    token_budget: int = 2000


# ── Roster ──────────────────────────────────────────────────────────────────

AGENTS: dict[str, AgentConfig] = {
    "kronos": AgentConfig(
        name="kronos",
        icon="+",
        role="Orchestrator — synthesizes outputs from other agents",
        color="#a78bfa",
        system_prefix=(
            "You are Kronos, the orchestrator. Your job is to synthesize "
            "multiple agent outputs into one coherent, actionable response. "
            "Be concise. Preserve key details from each agent. Resolve conflicts."
        ),
        obsidian_folders=["02-Runs/"],
        models=["gemma2:9b", "qwen2.5:7b"],
        token_budget=2500,  # synthesis needs more room
    ),
    "cipher": AgentConfig(
        name="cipher",
        icon="{}",
        role="Code — writes, reviews, and debugs code",
        color="#60a5fa",
        system_prefix=(
            "You are Cipher, the code agent. Write clean, minimal code. "
            "Prefer standard library. No unnecessary abstractions. "
            "Include brief inline comments only where logic is non-obvious."
        ),
        obsidian_folders=["03-Code/", "04-Tech-Specs/"],
        models=["qwen2.5:7b", "deepseek-coder:6.7b"],
    ),
    "scout": AgentConfig(
        name="scout",
        icon=">>",
        role="Research — finds, summarizes, and fact-checks information",
        color="#4ade80",
        system_prefix=(
            "You are Scout, the research agent. Summarize findings in bullet points. "
            "Cite sources when available. Flag uncertainty explicitly. "
            "Prioritize recent and primary sources."
        ),
        obsidian_folders=["05-Research/", "00-Inbox/"],
        models=["gemma2:9b", "phi3:mini"],
    ),
    "vision": AgentConfig(
        name="vision",
        icon="()",
        role="Images / Design — describes, critiques, and plans visual assets",
        color="#f472b6",
        system_prefix=(
            "You are Vision, the design agent. Describe visual concepts precisely. "
            "Reference colors by hex code. Use spatial language (top-left, below fold). "
            "Keep suggestions actionable for a developer or designer."
        ),
        obsidian_folders=["07-Brand/design/", "10-Design/"],
        models=["llava:7b", "bakllava"],
        token_budget=1500,  # vision models have smaller context
    ),
    "quill": AgentConfig(
        name="quill",
        icon='""',
        role="Writing — drafts copy, edits prose, maintains brand voice",
        color="#fb923c",
        system_prefix=(
            "You are Quill, the writing agent. Match the brand voice: direct, "
            "confident, no fluff. Use short sentences. Active voice. "
            "Every word must earn its place."
        ),
        obsidian_folders=["06-Content/", "07-Brand/"],
        models=["gemma2:9b", "qwen2.5:7b"],
    ),
    "atlas": AgentConfig(
        name="atlas",
        icon="#",
        role="Data / Analytics — queries, aggregates, and interprets data",
        color="#f59e0b",
        system_prefix=(
            "You are Atlas, the data agent. Present numbers with context. "
            "Use tables for comparisons. Flag statistical significance. "
            "Suggest next analysis steps."
        ),
        obsidian_folders=["08-Data/", "09-Analytics/"],
        models=["qwen2.5:7b", "gemma2:9b"],
    ),
    "pulse": AgentConfig(
        name="pulse",
        icon="~",
        role="Comms — drafts messages, manages channels, handles outreach",
        color="#38bdf8",
        system_prefix=(
            "You are Pulse, the comms agent. Write messages that are clear "
            "and human. Match the tone to the channel (formal for email, "
            "casual for Slack). Keep it short — one screen max."
        ),
        obsidian_folders=["11-Channels/", "12-Comms/"],
        models=["gemma2:9b", "phi3:mini"],
        token_budget=1800,
    ),
}


def get_agent(name: str) -> AgentConfig:
    """Retrieve agent config by name. Raises KeyError if unknown."""
    return AGENTS[name]


def agent_names() -> list[str]:
    """Return list of all agent names (for router prompt)."""
    return list(AGENTS.keys())


def roster_summary() -> str:
    """One-line-per-agent summary for the MiniMax router system prompt."""
    lines = []
    for a in AGENTS.values():
        if a.name == "kronos":
            continue  # kronos is the synthesizer, not a routable target
        lines.append(f"- {a.name}: {a.role}")
    return "\n".join(lines)
