use tauri::{
    image::Image,
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewWindow,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // No dock icon — pure menu bar app
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            // Build tray icon
            let icon = Image::from_path(
                app.path()
                    .resource_dir()
                    .unwrap()
                    .join("icons/32x32.png"),
            )
            .unwrap_or_else(|_| app.default_window_icon().unwrap().clone());

            let _tray = TrayIconBuilder::with_id("main")
                .icon(icon)
                .icon_as_template(true)
                .tooltip("KiroshiOS")
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        toggle_window(app);
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            // Hide (don't close) when user clicks outside the panel
            if let tauri::WindowEvent::Focused(false) = event {
                if window.label() == "main" {
                    let _ = window.hide();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn toggle_window(app: &AppHandle) {
    let window: WebviewWindow = app.get_webview_window("main").unwrap();
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        position_under_tray(app, &window);
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Position the popup panel just below the tray icon.
fn position_under_tray(app: &AppHandle, window: &WebviewWindow) {
    if let Some(tray) = app.tray_by_id("main") {
        if let Ok(Some(rect)) = tray.rect() {
            let monitor = window.current_monitor().ok().flatten();
            let scale = monitor.as_ref().map(|m| m.scale_factor()).unwrap_or(1.0);

            let (px, py) = match rect.position {
                tauri::Position::Physical(p) => (p.x as f64, p.y as f64),
                tauri::Position::Logical(p) => (p.x * scale, p.y * scale),
            };
            let (pw, ph) = match rect.size {
                tauri::Size::Physical(s) => (s.width as f64, s.height as f64),
                tauri::Size::Logical(s) => (s.width * scale, s.height * scale),
            };

            let x = (px / scale) as i32;
            let y = (py / scale) as i32;
            let icon_w = (pw / scale) as i32;
            let icon_h = (ph / scale) as i32;
            let win_w = 380i32;

            let new_x = x + icon_w / 2 - win_w / 2;
            let new_y = y + icon_h + 4;

            let _ = window.set_position(tauri::LogicalPosition::new(new_x, new_y));
        }
    }
}
