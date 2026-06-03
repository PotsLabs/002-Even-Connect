use std::sync::Mutex;

use tauri::{
    image::Image,
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewWindow,
};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

// ── App state ──────────────────────────────────────────────────────────────────

struct BackendProcess(Mutex<Option<CommandChild>>);

// Store the autostart CheckMenuItem so we can update its checkmark from the event handler
struct AutostartItem(Mutex<Option<CheckMenuItem<tauri::Wry>>>);

// When true, the panel will not auto-hide on focus loss (e.g. during BLE scanning)
struct HidePrevented(Mutex<bool>);

// ── Tauri commands ────────────────────────────────────────────────────────────

/// Called by the frontend to prevent the panel from hiding during a connection attempt.
#[tauri::command]
fn set_connection_active(state: tauri::State<'_, HidePrevented>, active: bool) {
    *state.0.lock().unwrap() = active;
}

// ── Entry point ───────────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .manage(BackendProcess(Mutex::new(None)))
        .manage(AutostartItem(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // Pure menu-bar app — no dock icon
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            // In release builds, spawn the Python backend sidecar.
            // In dev mode, start.sh already started the backend.
            #[cfg(not(debug_assertions))]
            spawn_backend(app.handle())?;

            // Build tray icon + context menu
            build_tray(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide (not close) when the panel loses focus — keeps backend alive
            if let tauri::WindowEvent::Focused(false) = event {
                if window.label() == "main" {
                    let _ = window.hide();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

// ── Backend sidecar ───────────────────────────────────────────────────────────

fn spawn_backend(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let (mut rx, child) = app.shell().sidecar("api")?.spawn()?;
    *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    log::info!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    log::warn!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(e) => {
                    log::error!("[backend] sidecar error: {}", e);
                }
                CommandEvent::Terminated(s) => {
                    log::warn!("[backend] sidecar exited: {:?}", s);
                }
                _ => {}
            }
        }
    });

    Ok(())
}

fn kill_backend(app: &AppHandle) {
    if let Some(child) = app.state::<BackendProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
}

// ── Tray icon + menu ──────────────────────────────────────────────────────────

fn build_tray(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let is_autolaunch = app.autolaunch().is_enabled().unwrap_or(false);

    let toggle_item = MenuItem::with_id(app, "toggle", "Show KiroshiOS", true, None::<&str>)?;
    let autostart_item = CheckMenuItem::with_id(
        app,
        "autostart",
        "Launch at Login",
        true,
        is_autolaunch,
        None::<&str>,
    )?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit KiroshiOS", true, None::<&str>)?;

    // Stash a clone so the menu event handler can flip the checkmark
    *app.state::<AutostartItem>().0.lock().unwrap() = Some(autostart_item.clone());

    let menu = Menu::with_items(
        app,
        &[
            &toggle_item,
            &PredefinedMenuItem::separator(app)?,
            &autostart_item,
            &PredefinedMenuItem::separator(app)?,
            &quit_item,
        ],
    )?;

    let icon = Image::from_path(
        app.path()
            .resource_dir()
            .unwrap()
            .join("icons/32x32.png"),
    )
    .unwrap_or_else(|_| app.default_window_icon().unwrap().clone());

    TrayIconBuilder::with_id("main")
        .icon(icon)
        .icon_as_template(true)
        .tooltip("KiroshiOS")
        .menu(&menu)
        // Left-click toggles the panel
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                toggle_window(tray.app_handle());
            }
        })
        // Right-click menu actions
        .on_menu_event(|app, event| match event.id.as_ref() {
            "toggle" => toggle_window(app),
            "autostart" => handle_autostart_toggle(app),
            "quit" => {
                #[cfg(not(debug_assertions))]
                kill_backend(app);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

// ── Autostart toggle ──────────────────────────────────────────────────────────

fn handle_autostart_toggle(app: &AppHandle) {
    let mgr = app.autolaunch();
    let currently_enabled = mgr.is_enabled().unwrap_or(false);

    if currently_enabled {
        let _ = mgr.disable();
    } else {
        let _ = mgr.enable();
    }

    // Sync the checkmark via the stored item reference
    if let Some(item) = app.state::<AutostartItem>().0.lock().unwrap().as_ref() {
        let _ = item.set_checked(!currently_enabled);
    }
}

// ── Window management ─────────────────────────────────────────────────────────

fn toggle_window(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else { return };
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        position_under_tray(app, &window);
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn position_under_tray(app: &AppHandle, window: &WebviewWindow) {
    let Some(tray) = app.tray_by_id("main") else { return };
    let Ok(Some(rect)) = tray.rect() else { return };

    let scale = window
        .current_monitor()
        .ok()
        .flatten()
        .map(|m| m.scale_factor())
        .unwrap_or(1.0);

    let (px, py) = match rect.position {
        tauri::Position::Physical(p) => (p.x as f64, p.y as f64),
        tauri::Position::Logical(p) => (p.x * scale, p.y * scale),
    };
    let (pw, ph) = match rect.size {
        tauri::Size::Physical(s) => (s.width as f64, s.height as f64),
        tauri::Size::Logical(s) => (s.width * scale, s.height * scale),
    };

    let icon_x = (px / scale) as i32;
    let icon_y = (py / scale) as i32;
    let icon_w = (pw / scale) as i32;
    let icon_h = (ph / scale) as i32;
    let win_w = 380i32;

    let _ = window.set_position(tauri::LogicalPosition::new(
        icon_x + icon_w / 2 - win_w / 2,
        icon_y + icon_h + 4,
    ));
}
