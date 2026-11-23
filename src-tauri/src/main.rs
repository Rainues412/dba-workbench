#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod dashboard;
mod desktop_db;
mod search;
mod tasks;

use std::{
    env, fs, io,
    path::{Path, PathBuf},
};

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    webview::NewWindowResponse,
    AppHandle, Manager, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent,
};

fn register_window(window: &WebviewWindow, port: u16) -> io::Result<()> {
    use windows_sys::Win32::UI::WindowsAndMessaging::SetPropW;
    let hwnd = window.hwnd().map_err(io::Error::other)?;
    let name: Vec<u16> = format!("DBAWorkbench.DesktopWindow.{port}")
        .encode_utf16()
        .chain([0])
        .collect();
    // The existing shortcut can now activate this window using the same Win32 property.
    if unsafe { SetPropW(hwnd.0, name.as_ptr(), std::ptr::dangling_mut()) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn open_external(url: &Url) {
    use windows_sys::Win32::UI::Shell::ShellExecuteW;
    if matches!(url.scheme(), "http" | "https") {
        let target: Vec<u16> = url.as_str().encode_utf16().chain([0]).collect();
        // Ask the Windows URL handler to open the link outside this privileged WebView.
        unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                std::ptr::null(),
                target.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            );
        }
    }
}

fn close_to_tray(settings: Option<&Path>) -> bool {
    settings
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|contents| serde_json::from_str::<serde_json::Value>(&contents).ok())
        .and_then(|settings| settings.get("close_to_tray")?.as_bool())
        .unwrap_or(true)
}

fn show_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn main() {
    let mut builder = tauri::Builder::default();
    if env::var_os("DBA_TAURI_PORT").is_none() {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
            show_window(app);
        }));
    }
    builder
        .setup(|app| {
            let data_dir = env::var_os("DBA_TAURI_DATA_DIR")
                .or_else(|| env::var_os("DBA_TAURI_DEV_DATA_DIR"))
                .map(PathBuf::from)
                .filter(|path| path.is_absolute())
                .ok_or_else(|| io::Error::other("请从工作台启动入口指定数据目录"))?;
            let db_path = data_dir.join("workspace.db");
            rusqlite::Connection::open_with_flags(
                &db_path,
                rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
            )?;
            let source_port = env::var("DBA_TAURI_PORT")
                .ok()
                .map(|port| port.parse::<u16>())
                .transpose()?;
            let (mut url, token) = if let Some(port) = source_port {
                (
                    Url::parse(&format!("http://127.0.0.1:{port}/"))?,
                    env::var("DBA_TAURI_DESKTOP_TOKEN")?,
                )
            } else {
                let url = app
                    .config()
                    .build
                    .dev_url
                    .clone()
                    .ok_or_else(|| io::Error::other("缺少迁移预览地址"))?;
                (url, env::var("DBA_TAURI_DEV_DESKTOP_TOKEN")?)
            };
            app.manage(desktop_db::Workspace {
                path: db_path,
                origin: url.clone(),
            });
            let origin = url.origin();
            url.set_fragment(Some(&format!("desktop={token}")));

            let open = MenuItem::with_id(app, "open", "打开工作台", true, None::<&str>)?;
            let exit = MenuItem::with_id(app, "exit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &exit])?;
            let mut tray = TrayIconBuilder::new()
                .tooltip("DBA 工作台")
                .show_menu_on_left_click(false)
                .menu(&menu)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "open" => show_window(app),
                    "exit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_window(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            let mut config = app.config().app.windows[0].clone();
            config.url = WebviewUrl::External(url);
            config.visible = env::var("DBA_TAURI_SILENT").as_deref() != Ok("1");
            let profile = env::var_os("DBA_TAURI_WEBVIEW")
                .map(PathBuf::from)
                .unwrap_or_else(|| data_dir.join("webview"));
            let settings = env::var_os("DBA_TAURI_DESKTOP_SETTINGS").map(PathBuf::from);
            let window = WebviewWindowBuilder::from_config(app, &config)?
                .data_directory(profile)
                .on_navigation(move |url| url.origin() == origin)
                .on_new_window(|url, _| {
                    open_external(&url);
                    NewWindowResponse::Deny
                })
                .build()?;
            if let Some(port) = source_port {
                register_window(&window, port)?;
            }
            let workbench = window.clone();
            window.on_window_event(move |event| {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    if !close_to_tray(settings.as_deref()) {
                        workbench.app_handle().exit(0);
                        return;
                    }
                    let _ = workbench.hide();
                    // Match the current desktop window's release of page memory and unlocked keys.
                    let _ = workbench.eval("window.location.reload()");
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            dashboard::dashboard_stats,
            dashboard::dashboard_recent_tasks,
            dashboard::dashboard_database_distribution,
            tasks::tasks_list,
            tasks::tasks_detail,
            tasks::tasks_create,
            tasks::tasks_update,
            tasks::tasks_delete,
            search::global_search,
        ])
        .run(tauri::generate_context!())
        .expect("failed to start the DBA Workbench migration preview");
}
