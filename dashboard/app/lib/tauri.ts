/**
 * tauri.ts — Tauri environment detection and IPC bridge.
 *
 * When running inside Tauri, uses IPC commands for backend lifecycle.
 * When running as a standalone web app, falls back to env vars / defaults.
 */

/** Check if we're running inside a Tauri webview. */
export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

/**
 * Get the backend URL (HTTP base).
 * In Tauri: asks the Rust shell for the sidecar port.
 * In browser: uses NEXT_PUBLIC_API_URL or defaults to localhost:8765.
 */
export async function getBackendUrl(): Promise<string> {
  if (isTauri()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      return await invoke<string>("get_backend_url");
    } catch {
      // Fallback if Tauri API fails
      return "http://localhost:8765";
    }
  }
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765";
}

/**
 * Get the WebSocket base URL.
 * Derives from the HTTP backend URL (http → ws, https → wss).
 */
export async function getWsUrl(): Promise<string> {
  const http = await getBackendUrl();
  return http.replace(/^http/, "ws");
}

/** Ask Tauri to check backend health (no-op in browser mode). */
export async function checkBackendHealth(): Promise<{
  status: string;
  ollama: string;
  remote: string | null;
} | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke("backend_health");
  } catch {
    return null;
  }
}

/** Ask Tauri to restart the backend sidecar. */
export async function restartBackend(): Promise<string | null> {
  if (!isTauri()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("stop_backend");
    return await invoke<string>("start_backend");
  } catch (e) {
    return `restart failed: ${e}`;
  }
}
