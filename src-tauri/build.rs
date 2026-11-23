const COMMANDS: &[&str] = &[
    "dashboard_stats",
    "dashboard_recent_tasks",
    "dashboard_database_distribution",
    "tasks_list",
    "tasks_detail",
    "tasks_create",
    "tasks_update",
    "tasks_delete",
    "global_search",
];

fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(COMMANDS)),
    )
    .expect("failed to configure the DBA Workbench desktop application");
}
