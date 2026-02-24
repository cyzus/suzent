use std::fs;
use std::path::Path;

fn main() {
    // Ensure resource placeholder files exist so Tauri bundler doesn't fail.
    // The actual shim scripts are generated at runtime by ensure_cli_shim().
    let resources = Path::new("resources");
    fs::create_dir_all(resources).expect("Failed to create resources directory");

    let cmd_shim = resources.join("suzent.cmd");
    if !cmd_shim.exists() {
        fs::write(&cmd_shim, "@echo off\r\nREM Placeholder — actual shim is generated at runtime.\r\n")
            .expect("Failed to write suzent.cmd placeholder");
    }

    let sh_shim = resources.join("suzent");
    if !sh_shim.exists() {
        fs::write(&sh_shim, "#!/bin/sh\n# Placeholder — actual shim is generated at runtime.\n")
            .expect("Failed to write suzent placeholder");
    }

    tauri_build::build()
}
