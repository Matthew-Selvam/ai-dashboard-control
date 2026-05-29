"""
token_optimizer.py — Per-subtask context compression + budget enforcement.
==========================================================================

Before each subtask is dispatched:
  1. Load context from Obsidian vault (scoped to agent's folders)
  2. Compress to the most relevant ~800 tokens for that agent
  3. Prepend agent-specific system prompt prefix
  4. Verify total <= agent's token_budget (default 2000)

Token counting: chars / 4 approximation (no tiktoken dependency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import agents
import context_loader
from minimax_router import Subtask


# ── Config ──────────────────────────────────────────────────────────────────

CONTEXT_TOKEN_BUDGET = 800     # max tokens for compressed context
MIN_CONTEXT_TOKENS = 50        # below this, skip context entirely
CHARS_PER_TOKEN = 4            # approximation: 1 token ~ 4 chars


# ── Data types ──────────────────────────────────────────────────────────────

@dataclass
class OptimizedMessages:
    """Ready-to-dispatch messages list + token accounting."""
    messages: list[dict[str, str]]
    tokens_system: int
    tokens_context: int
    tokens_prompt: int
    tokens_total: int
    agent: str
    subtask_id: str


# ── Public API ──────────────────────────────────────────────────────────────

def optimize(subtask: Subtask) -> OptimizedMessages:
    """
    Build the optimized messages[] for a subtask.

    Returns messages ready for Ollama/OpenRouter dispatch,
    with token counts for tracing.
    """
    agent_cfg = agents.get_agent(subtask.agent)
    budget = agent_cfg.token_budget

    # 1. Agent system prefix (fixed cost)
    system_prefix = agent_cfg.system_prefix
    tokens_system = _count_tokens(system_prefix)

    # 2. User prompt (fixed cost)
    tokens_prompt = _count_tokens(subtask.prompt)

    # 3. Remaining budget for context
    remaining = budget - tokens_system - tokens_prompt
    ctx_budget = min(CONTEXT_TOKEN_BUDGET, max(0, remaining))

    # 4. Load + compress context
    context_text = ""
    tokens_context = 0

    if ctx_budget >= MIN_CONTEXT_TOKENS:
        raw_context = context_loader.get_context(
            subtask.prompt,
            folders=list(agent_cfg.obsidian_folders),
        )
        if raw_context:
            context_text = _compress(
                raw_context,
                query=f"{subtask.prompt} {subtask.context_slice}",
                token_budget=ctx_budget,
            )
            tokens_context = _count_tokens(context_text)

    # 5. Build messages
    system_content = system_prefix
    if context_text:
        system_content += f"\n\n---\nContext:\n{context_text}\n---"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": subtask.prompt},
    ]

    tokens_total = tokens_system + tokens_context + tokens_prompt

    # 6. Emergency trim if still over budget
    if tokens_total > budget:
        overage = tokens_total - budget
        # Trim context first
        if tokens_context > 0:
            trim_chars = overage * CHARS_PER_TOKEN
            context_text = context_text[:-trim_chars] if trim_chars < len(context_text) else ""
            tokens_context = _count_tokens(context_text)
            system_content = system_prefix
            if context_text:
                system_content += f"\n\n---\nContext:\n{context_text}\n---"
            messages[0]["content"] = system_content
            tokens_total = tokens_system + tokens_context + tokens_prompt

    return OptimizedMessages(
        messages=messages,
        tokens_system=tokens_system,
        tokens_context=tokens_context,
        tokens_prompt=tokens_prompt,
        tokens_total=tokens_total,
        agent=subtask.agent,
        subtask_id=subtask.id,
    )


# ── Token counting ──────────────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """Approximate token count. chars / 4, minimum 1 if non-empty."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


# ── Context compression ────────────────────────────────────────────────────

def _compress(raw_context: str, query: str, token_budget: int) -> str:
    """
    Compress raw context to fit within token_budget.

    Strategy:
      1. Split into sentences
      2. Score each by keyword overlap with query
      3. Take top-scoring sentences (in original order) until budget filled
    """
    sentences = _split_sentences(raw_context)
    if not sentences:
        return ""

    # Extract query keywords (lowered, unique, len > 2)
    query_words = set(
        w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", query.lower())
    )

    # Score each sentence
    scored: list[tuple[int, int, str]] = []  # (score, original_index, sentence)
    for idx, sent in enumerate(sentences):
        sent_lower = sent.lower()
        score = sum(1 for w in query_words if w in sent_lower)
        # Boost sentences with proper nouns or technical terms (capitalized words)
        caps = len(re.findall(r"\b[A-Z][a-z]+", sent))
        score += caps
        scored.append((score, idx, sent))

    # Sort by score descending, take top until budget filled
    scored.sort(key=lambda x: -x[0])

    budget_chars = token_budget * CHARS_PER_TOKEN
    selected: list[tuple[int, str]] = []  # (original_index, sentence)
    used_chars = 0

    for score, idx, sent in scored:
        if score == 0 and selected:
            break  # stop adding zero-relevance sentences once we have some content
        sent_chars = len(sent)
        if used_chars + sent_chars > budget_chars:
            # Try to fit a truncated version
            remaining = budget_chars - used_chars
            if remaining > 80:  # worth including a partial sentence
                selected.append((idx, sent[:remaining]))
                used_chars += remaining
            break
        selected.append((idx, sent))
        used_chars += sent_chars

    if not selected:
        # Nothing scored — take first N chars as fallback
        return raw_context[:budget_chars]

    # Restore original document order
    selected.sort(key=lambda x: x[0])
    return " ".join(s for _, s in selected)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Simple regex splitter."""
    # Split on period/exclamation/question followed by space+uppercase or end
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    # Also split on double newlines (paragraph breaks)
    result = []
    for p in parts:
        for sub in p.split("\n\n"):
            stripped = sub.strip()
            if stripped:
                result.append(stripped)
    return result
