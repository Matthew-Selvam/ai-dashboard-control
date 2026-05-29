"""
context_loader.py
=================
Loads relevant context from:
  1. Obsidian vault  (~/Documents/ObsidianVault/CommandCenter)
  2. graphify graph  (graphify-out/graph.json in the project dir, if present)

Called by supervisor.py before dispatching each task so the model
has access to project briefs, brand notes, tech specs, etc.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OBSIDIAN_ROOT  = Path(os.getenv("OBSIDIAN_ROOT",
    str(Path.home() / "Documents" / "ObsidianVault" / "CommandCenter")))
GRAPHIFY_BIN   = Path(os.getenv("GRAPHIFY_BIN",
    str(Path.home() / ".local" / "bin" / "graphify")))
PROJECT_ROOT   = Path(__file__).parent   # ai-dashboard-control/

MAX_CONTEXT_CHARS = 4000   # total cap across all injected snippets
MAX_FILE_CHARS    = 2000   # per-file truncation limit
MAX_KEYWORDS      = 10     # how many keywords to grep for
TOP_FILES         = 4      # how many Obsidian files to include

# Words that carry no signal for vault search
STOP_WORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of","with",
    "by","from","up","about","into","through","me","my","i","we","you","it",
    "is","are","was","were","be","been","have","has","had","do","does","did",
    "will","would","could","should","may","might","can","get","all","this",
    "that","these","also","just","more","make","need","give","tell","write",
    "create","what","how","when","where","why","who","which","please","help",
    "want","like","use","its","our","your","their","there","here","then",
    "than","so","if","not","no","yes","any","some","much","many","very",
}


# ── Keyword extraction ────────────────────────────────────────────────────────

def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
    seen, out = set(), []
    for w in words:
        if w not in STOP_WORDS and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ── Obsidian search ───────────────────────────────────────────────────────────

def _search_obsidian(keywords: list[str]) -> list[tuple[int, Path]]:
    """Return (hit_count, path) sorted by relevance.

    Longer / more specific keywords (likely proper nouns or project names)
    get a boosted weight so that a file uniquely matching 'offsidesupply'
    outranks a file that only matches common words like 'content' or 'strategy'.
    """
    if not OBSIDIAN_ROOT.exists():
        return []

    hits: dict[Path, int] = {}
    for kw in keywords[:MAX_KEYWORDS]:
        try:
            r = subprocess.run(
                ["grep", "-r", "-l", "-i", "--include=*.md", kw, str(OBSIDIAN_ROOT)],
                capture_output=True, text=True, timeout=5,
            )
            matched = [Path(l) for l in r.stdout.strip().splitlines() if l]
            if not matched:
                continue
            # Specificity boost: the fewer files a keyword appears in, the more
            # diagnostic it is. 1 file = weight 20, 2 = 10, 3–5 = 5, else = 1.
            # Also multiply by length bonus for longer (more unique) words.
            specificity = 20 if len(matched) == 1 else (10 if len(matched) == 2
                          else (5 if len(matched) <= 5 else 1))
            length_bonus = max(1, len(kw) - 5)
            weight = specificity * length_bonus
            for p in matched:
                hits[p] = hits.get(p, 0) + weight
        except Exception:
            continue

    return sorted(hits.items(), key=lambda x: -x[1])


def _read_file(path: Path, max_chars: int = MAX_FILE_CHARS) -> str:
    try:
        text = path.read_text(errors="ignore").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(truncated)"
        return text
    except Exception:
        return ""


# ── Graphify ──────────────────────────────────────────────────────────────────

def _query_graphify(query: str) -> str:
    if not GRAPHIFY_BIN.exists():
        return ""
    # Look for a graph in the project root or any sibling code dir
    candidates = [PROJECT_ROOT]
    try:
        candidates += [p for p in (Path.home() / "code").iterdir() if p.is_dir()]
    except Exception:
        pass

    for d in candidates:
        if (d / "graphify-out" / "graph.json").exists():
            try:
                r = subprocess.run(
                    [str(GRAPHIFY_BIN), "query", query],
                    capture_output=True, text=True, timeout=10, cwd=str(d),
                )
                out = r.stdout.strip()
                if out:
                    return out[:1200]
            except Exception:
                pass
    return ""


# ── Public API ────────────────────────────────────────────────────────────────

def get_context(task: str) -> str:
    """
    Return a markdown context block to inject into the supervisor system message.
    Returns empty string if nothing relevant was found.
    """
    keywords = _keywords(task)
    if not keywords:
        return ""

    parts: list[str] = []
    used_chars = 0

    # --- Obsidian ---
    ranked = _search_obsidian(keywords)
    for path, _hits in ranked[:TOP_FILES]:
        remaining = MAX_CONTEXT_CHARS - used_chars
        if remaining <= 200:
            break
        content = _read_file(path, max_chars=min(MAX_FILE_CHARS, remaining))
        if content:
            parts.append(f"### [{path.stem}]\n{content}")
            used_chars += len(content)

    # --- Graphify ---
    remaining = MAX_CONTEXT_CHARS - used_chars
    if remaining > 300:
        gq = _query_graphify(task)
        if gq:
            parts.append(f"### [Knowledge Graph]\n{gq}")

    if not parts:
        return ""

    header = (
        "You have access to the following context from the user's knowledge base. "
        "Use it to give accurate, project-aware answers.\n\n"
    )
    return header + "\n\n".join(parts) + "\n\n---\n\n"
