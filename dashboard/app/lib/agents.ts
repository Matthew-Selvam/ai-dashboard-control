/**
 * agents.ts — TS mirror of agents.py (single source of truth).
 *
 * Keep in sync with the Python roster. The dashboard uses this for
 * the sidebar, agent cards, and task graph visualization.
 */

export interface AgentConfig {
  name: string;
  icon: string;
  role: string;
  color: string;
  models: string[];
  tokenBudget: number;
  obsidianFolders: string[];
}

export const AGENTS: Record<string, AgentConfig> = {
  kronos: {
    name: "kronos",
    icon: "+",
    role: "Orchestrator",
    color: "#a78bfa",
    models: ["gemma2:9b", "qwen2.5:7b"],
    tokenBudget: 2500,
    obsidianFolders: ["02-Runs/"],
  },
  cipher: {
    name: "cipher",
    icon: "{}",
    role: "Code",
    color: "#60a5fa",
    models: ["qwen2.5:7b", "deepseek-coder:6.7b"],
    tokenBudget: 2000,
    obsidianFolders: ["03-Code/", "04-Tech-Specs/"],
  },
  scout: {
    name: "scout",
    icon: ">>",
    role: "Research",
    color: "#4ade80",
    models: ["gemma2:9b", "phi3:mini"],
    tokenBudget: 2000,
    obsidianFolders: ["05-Research/", "00-Inbox/"],
  },
  vision: {
    name: "vision",
    icon: "()",
    role: "Images / Design",
    color: "#f472b6",
    models: ["llava:7b", "bakllava"],
    tokenBudget: 1500,
    obsidianFolders: ["07-Brand/design/", "10-Design/"],
  },
  quill: {
    name: "quill",
    icon: '""',
    role: "Writing",
    color: "#fb923c",
    models: ["gemma2:9b", "qwen2.5:7b"],
    tokenBudget: 2000,
    obsidianFolders: ["06-Content/", "07-Brand/"],
  },
  atlas: {
    name: "atlas",
    icon: "#",
    role: "Data / Analytics",
    color: "#f59e0b",
    models: ["qwen2.5:7b", "gemma2:9b"],
    tokenBudget: 2000,
    obsidianFolders: ["08-Data/", "09-Analytics/"],
  },
  pulse: {
    name: "pulse",
    icon: "~",
    role: "Comms",
    color: "#38bdf8",
    models: ["gemma2:9b", "phi3:mini"],
    tokenBudget: 1800,
    obsidianFolders: ["11-Channels/", "12-Comms/"],
  },
};

/** Agent names in display order (kronos first). */
export const AGENT_ORDER = [
  "kronos", "cipher", "scout", "vision", "quill", "atlas", "pulse",
] as const;

/** Get agent config by name. */
export function getAgent(name: string): AgentConfig | undefined {
  return AGENTS[name];
}

/** Routable agents (excludes kronos — it's the synthesizer). */
export const ROUTABLE_AGENTS = AGENT_ORDER.filter((a) => a !== "kronos");
