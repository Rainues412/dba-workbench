use std::{io, thread, time::Duration};

use tauri::{AppHandle, Manager, State, WebviewWindow};
use windows_sys::Win32::UI::WindowsAndMessaging::{GetPropW, RemovePropW, SetPropW};

use crate::desktop_db::Workspace;

const PENDING: &str = "DBAWorkbench.WaitingForPaint";
const REQUESTED: &str = "DBAWorkbench.ShowAfterPaint";
const STARTED: &str = "DBAWorkbench.PaintedOnce";

fn property_name(name: &str) -> Vec<u16> {
    name.encode_utf16().chain([0]).collect()
}

fn has(window: &WebviewWindow, name: &str) -> bool {
    window
        .hwnd()
        .is_ok_and(|hwnd| !unsafe { GetPropW(hwnd.0, property_name(name).as_ptr()) }.is_null())
}

fn set(window: &WebviewWindow, name: &str) -> io::Result<()> {
    let hwnd = window.hwnd().map_err(io::Error::other)?;
    if unsafe {
        SetPropW(
            hwnd.0,
            property_name(name).as_ptr(),
            std::ptr::dangling_mut(),
        )
    } == 0
    {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn clear(window: &WebviewWindow, name: &str) -> bool {
    window
        .hwnd()
        .is_ok_and(|hwnd| !unsafe { RemovePropW(hwnd.0, property_name(name).as_ptr()) }.is_null())
}

pub fn prepare(window: &WebviewWindow, show_when_ready: bool) -> io::Result<()> {
    if show_when_ready {
        set(window, REQUESTED)?;
    } else {
        clear(window, REQUESTED);
    }
    set(window, PENDING)
}

pub fn watch_startup(window: WebviewWindow) {
    let app = window.app_handle().clone();
    thread::spawn(move || {
        thread::sleep(Duration::from_secs(20));
        let _ = app.run_on_main_thread(move || {
            if !has(&window, STARTED) {
                eprintln!("Workbench frontend did not complete its initial render");
                window.app_handle().exit(1);
            }
        });
    });
}

pub fn register(window: &WebviewWindow, port: u16) -> io::Result<()> {
    set(window, &format!("DBAWorkbench.DesktopWindow.{port}"))
}

pub fn request_show(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if has(&window, PENDING) {
            let _ = set(&window, REQUESTED);
        } else {
            show(&window);
        }
    }
}

fn show(window: &WebviewWindow) {
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
}

#[tauri::command]
pub fn desktop_painted(
    window: WebviewWindow,
    workspace: State<'_, Workspace>,
) -> Result<(), String> {
    let url = window.url().map_err(|error| error.to_string())?;
    if window.label() != "main" || url.origin() != workspace.origin.origin() {
        return Err("Unrecognized desktop window".into());
    }
    set(&window, STARTED).map_err(|error| error.to_string())?;
    if clear(&window, PENDING) && clear(&window, REQUESTED) {
        show(&window);
    }
    Ok(())
}
