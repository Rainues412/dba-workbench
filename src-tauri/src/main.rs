#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod account;
mod customers;
mod dashboard;
mod desktop_db;
mod libraries;
mod resources;
mod search;
mod tasks;
mod window_visibility;

use std::{
    env, fs, io,
    path::{Path, PathBuf},
};

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    webview::NewWindowResponse,
    Manager, Url, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};

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

fn main() {
    let mut builder = tauri::Builder::default();
    if env::var_os("DBA_TAURI_PORT").is_none() {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _, _| {
            window_visibility::request_show(app);
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
                    "open" => window_visibility::request_show(app),
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
                        window_visibility::request_show(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;

            let mut config = app.config().app.windows[0].clone();
            config.url = WebviewUrl::External(url);
            config.visible = false;
            let show_when_ready = env::var("DBA_TAURI_SILENT").as_deref() != Ok("1");
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
            window_visibility::prepare(&window, show_when_ready)?;
            if let Some(port) = source_port {
                window_visibility::register(&window, port)?;
            }
            window_visibility::watch_startup(window.clone());
            let workbench = window.clone();
            window.on_window_event(move |event| {
                if let WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    if !close_to_tray(settings.as_deref()) {
                        workbench.app_handle().exit(0);
                        return;
                    }
                    if window_visibility::prepare(&workbench, false).is_ok() {
                        let _ = workbench.hide();
                        // Reload while hidden to release page memory and unlocked keys.
                        if workbench.reload().is_err() {
                            workbench.app_handle().exit(1);
                        }
                    }
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
            resources::resources_list,
            resources::resources_facets,
            resources::resources_detail,
            resources::resources_create,
            resources::resources_update,
            resources::resources_delete,
            customers::customers_list,
            customers::customers_detail,
            customers::customers_create,
            customers::customers_update,
            customers::customers_delete,
            libraries::library_list,
            libraries::library_facets,
            libraries::library_detail,
            libraries::library_create,
            libraries::library_update,
            libraries::library_delete,
            libraries::script_recent_views,
            libraries::script_record_view,
            libraries::script_version,
            search::global_search,
            window_visibility::desktop_painted,
            account::account_status,
            account::vault_profile,
        ])
        .run(tauri::generate_context!())
        .expect("failed to start the DBA Workbench migration preview");
}
