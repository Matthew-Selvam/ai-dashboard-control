// AI Dashboard Control — Tauri v2 shell
//
// Manages the Python FastAPI sidecar (server.py) lifecycle and exposes
// IPC commands for the Next.js dashboard webview.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod ipc;
mod sidecar;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Spawn the Python backend sidecar on app launch
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::spawn_backend(&handle).await {
                    eprintln!("[tauri] failed to start backend: {e}");
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            ipc::start_backend,
            ipc::stop_backend,
            ipc::backend_health,
            ipc::get_backend_url,
        ])
        .run(tauri::generate_context!())
        .expect("error while running AI Dashboard Control");
}
