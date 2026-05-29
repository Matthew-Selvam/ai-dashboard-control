// ipc.rs — Tauri IPC command handlers.
//
// These are invokable from the Next.js webview via @tauri-apps/api/core.

use crate::sidecar;

/// Spawn the Python backend sidecar.
#[tauri::command]
pub async fn start_backend(handle: tauri::AppHandle) -> Result<String, String> {
    sidecar::spawn_backend(&handle).await?;
    Ok(format!("Backend started on port {}", sidecar::BACKEND_PORT))
}

/// Kill the Python backend sidecar.
#[tauri::command]
pub fn stop_backend() -> String {
    sidecar::kill_backend();
    "Backend stopped".into()
}

/// Check backend health. Returns JSON status.
#[tauri::command]
pub async fn backend_health() -> Result<serde_json::Value, String> {
    let url = format!("http://localhost:{}/api/health", sidecar::BACKEND_PORT);
    let resp = reqwest::get(&url)
        .await
        .map_err(|e| format!("health check failed: {e}"))?;

    let body: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("parse error: {e}"))?;

    Ok(body)
}

/// Return the backend URL for the webview to connect to.
#[tauri::command]
pub fn get_backend_url() -> String {
    format!("http://localhost:{}", sidecar::BACKEND_PORT)
}
