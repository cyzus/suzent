use std::fs;
use std::path::Path;

fn main() {
    // Ensure resource placeholder files exist so Tauri bundler doesn't fail.
    // The actual shim scripts are generated at runtime by ensure_cli_shim().
    let resources = Path::new("resources");
    fs::create_dir_all(resources).expect("Failed to create resources directory");

    let cmd_shim = resources.join("suzent.cmd");
    if !cmd_shim.exists() {
        fs::write(
            &cmd_shim,
            "@echo off\r\nREM Placeholder — actual shim is generated at runtime.\r\n",
        )
        .expect("Failed to write suzent.cmd placeholder");
    }

    let sh_shim = resources.join("suzent");
    if !sh_shim.exists() {
        fs::write(
            &sh_shim,
            "#!/bin/sh\n# Placeholder — actual shim is generated at runtime.\n",
        )
        .expect("Failed to write suzent placeholder");
    }

    // Read with option_env! in backend::find_data_dir (side-by-side test builds).
    println!("cargo:rerun-if-env-changed=SUZENT_DATA_DIR_NAME");

    tauri_build::build()
}
