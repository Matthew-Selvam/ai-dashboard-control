// sidecar.rs — Manage the Python FastAPI backend as a child process.
//
// Spawn on app launch, kill on app quit, health-check loop.

use std::sync::Mutex;
use tauri::AppHandle;

/// Port the backend listens on.
pub const BACKEND_PORT: u16 = 8765;

/// Stored PID of the sidecar process (for cleanup).
static SIDECAR_PID: Mutex<Option<u32>> = Mutex::new(None);

/// Spawn `python3 server.py --port 8765` from the project root.
///
/// The project root is resolved relative to the Tauri resource directory
/// in production, or via `CARGO_MANIFEST_DIR/../` in dev.
pub async fn spawn_backend(handle: &AppHandle) -> Result<(), String> {
    use tauri_plugin_shell::ShellExt;

    let shell = handle.shell();
    let (mut rx, child) = shell
        .sidecar("python-backend")
        .map_err(|e| format!("sidecar config error: {e}"))?
        .spawn()
        .map_err(|e| format!("spawn error: {e}"))?;

    // Store PID for later cleanup
    *SIDECAR_PID.lock().unwrap() = Some(child.pid());

    // Stream sidecar stdout/stderr to Tauri console
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[backend] terminated: {:?}", payload);
                    break;
                }
                _ => {}
            }
        }
    });

    // Wait for backend to be ready (poll /api/health)
    for _ in 0..20 {
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        if check_health().await {
            println!("[tauri] backend ready on port {BACKEND_PORT}");
            return Ok(());
        }
    }

    Err("backend failed to start within 10s".into())
}

/// Kill the sidecar if it's running.
pub fn kill_backend() {
    if let Some(pid) = SIDECAR_PID.lock().unwrap().take() {
        #[cfg(unix)]
        {
            unsafe {
                libc::kill(pid as i32, libc::SIGTERM);
            }
        }
        println!("[tauri] killed backend pid {pid}");
    }
}

/// Check if the backend is responding.
pub async fn check_health() -> bool {
    let url = format!("http://localhost:{BACKEND_PORT}/api/health");
    reqwest::get(&url).await.map(|r| r.status().is_success()).unwrap_or(false)
}
