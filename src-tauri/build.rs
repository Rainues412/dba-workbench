const COMMANDS: &[&str] = &[
    "dashboard_stats",
    "dashboard_recent_tasks",
    "dashboard_database_distribution",
    "tasks_list",
    "tasks_detail",
    "tasks_create",
    "tasks_update",
    "tasks_delete",
    "resources_list",
    "resources_facets",
    "resources_detail",
    "resources_create",
    "resources_update",
    "resources_delete",
    "library_list",
    "library_facets",
    "library_detail",
    "library_create",
    "library_update",
    "library_delete",
    "script_recent_views",
    "script_record_view",
    "script_version",
    "global_search",
    "desktop_painted",
];

fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(COMMANDS)),
    )
    .expect("failed to configure the DBA Workbench desktop application");
}
