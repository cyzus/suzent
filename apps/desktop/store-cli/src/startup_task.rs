//! Start at login through the package's `Windows.ApplicationModel.StartupTask`.
//! Prints the state as JSON for the app (apps/desktop/src/storeStartup.ts).

use serde_json::{json, Value};

/// Must match `<desktop:StartupTask TaskId="...">` in
/// `packaging/msix/AppxManifest.template.xml`.
#[cfg_attr(not(windows), allow(dead_code))]
pub const STARTUP_TASK_ID: &str = "SuzentStartup";

#[cfg(windows)]
pub fn run(action: &str) -> Result<Value, String> {
    use windows::core::HSTRING;
    use windows::ApplicationModel::{StartupTask, StartupTaskState};

    let task = StartupTask::GetAsync(&HSTRING::from(STARTUP_TASK_ID))
        .and_then(|op| op.get())
        .map_err(|error| format!("Startup task '{STARTUP_TASK_ID}' is unavailable: {error}"))?;
    let state = match action {
        "enable" => task
            .RequestEnableAsync()
            .and_then(|op| op.get())
            .map_err(|error| format!("Cannot enable start at login: {error}"))?,
        "disable" => {
            task.Disable()
                .map_err(|error| format!("Cannot disable start at login: {error}"))?;
            task.State()
                .map_err(|error| format!("Cannot read start at login: {error}"))?
        }
        "status" => task
            .State()
            .map_err(|error| format!("Cannot read start at login: {error}"))?,
        other => return Err(format!("Unknown startup task action: {other}")),
    };
    let name = match state {
        StartupTaskState::Enabled => "enabled",
        StartupTaskState::DisabledByUser => "disabled_by_user",
        StartupTaskState::DisabledByPolicy => "disabled_by_policy",
        StartupTaskState::EnabledByPolicy => "enabled_by_policy",
        _ => "disabled",
    };
    Ok(describe(name))
}

#[cfg(not(windows))]
pub fn run(_action: &str) -> Result<Value, String> {
    Err("Start at login through the package is only available on Windows.".to_string())
}

#[cfg_attr(not(windows), allow(dead_code))]
/// `enabled`, plus an `error` for states only the user or an admin can change.
pub fn describe(state: &str) -> Value {
    let error = match state {
        "disabled_by_user" => Some(
            "Start at login was turned off in Windows Settings > Apps > Startup (or Task Manager). Turn Suzent back on there.",
        ),
        "disabled_by_policy" => Some("Start at login is disabled by your organization's policy."),
        _ => None,
    };
    json!({
        "state": state,
        "enabled": matches!(state, "enabled" | "enabled_by_policy"),
        "error": error,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn task_id_matches_manifest_template() {
        let manifest = include_str!("../../../../packaging/msix/AppxManifest.template.xml");
        assert!(manifest.contains(&format!("TaskId=\"{STARTUP_TASK_ID}\"")));
    }

    #[test]
    fn user_disabled_task_explains_where_to_turn_it_on() {
        let value = describe("disabled_by_user");
        assert_eq!(value["enabled"], false);
        assert!(value["error"].as_str().unwrap().contains("Settings"));
        assert_eq!(describe("enabled_by_policy")["enabled"], true);
    }
}
