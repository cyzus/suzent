//! Mainland China network support: deciding when to use domestic mirrors and
//! resolving release downloads through them with GitHub as the fallback.
//!
//! The decision is made from the network the installer is actually on, not
//! from the system language: a Chinese-language system abroad keeps GitHub,
//! and an English-language system in mainland China gets the mirrors.

use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;
use std::thread;
use std::time::Duration;

/// npmmirror syncs this repository's GitHub releases under this category once
/// it is listed in cnpm/binary-mirror-config. Until then every lookup falls
/// back to GitHub.
pub const MIRROR_RELEASE_BASE: &str = "https://registry.npmmirror.com/-/binary/suzent";
pub const GITHUB_RELEASE_BASE: &str = "https://github.com/cyzus/suzent/releases/download";
const GITHUB_LATEST_RELEASE: &str = "https://github.com/cyzus/suzent/releases/latest";
const LATEST_RELEASE_API: &str = "https://api.github.com/repos/cyzus/suzent/releases/latest";
pub const GITHUB_REPO_URL: &str = "https://github.com/cyzus/suzent.git";
/// Gitee pull-mirrors the GitHub repository, tags and branches included.
pub const GITEE_REPO_URL: &str = "https://gitee.com/cyzus/suzent.git";
const PYPI_MIRROR: &str = "https://pypi.tuna.tsinghua.edu.cn/simple";
/// Reachable from anywhere except behind the mainland firewall.
const GLOBAL_PROBE_URL: &str = "https://www.google.com/generate_204";
const CHINA_PROBE_URL: &str = "https://registry.npmmirror.com/";
const PROBE_TIMEOUT: Duration = Duration::from_secs(4);
const PREFERENCE_FILE: &str = "china-mirror";
const REGION_FILE: &str = "network-region";

static CHINA_MODE: OnceLock<bool> = OnceLock::new();

/// Explicit choice from `--china-mirror` / `--no-china-mirror`, then
/// `SUZENT_CHINA_MIRROR`, then the choice saved by the installer UI. `None`
/// means "decide from the network".
pub fn explicit_preference(args: &[String]) -> Option<bool> {
    if args.iter().any(|arg| arg == "--china-mirror") {
        return Some(true);
    }
    if args.iter().any(|arg| arg == "--no-china-mirror") {
        return Some(false);
    }
    env::var("SUZENT_CHINA_MIRROR")
        .ok()
        .and_then(|value| parse_preference(&value))
        .or_else(saved_preference)
}

/// Parses an on/off value; `auto` and unknown values defer to detection.
pub fn parse_preference(value: &str) -> Option<bool> {
    match value.trim().to_ascii_lowercase().as_str() {
        "1" | "true" | "yes" | "on" | "cn" | "china" => Some(true),
        "0" | "false" | "no" | "off" | "global" => Some(false),
        _ => None,
    }
}

fn preference_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".suzent")
        .join(PREFERENCE_FILE)
}

pub fn saved_preference() -> Option<bool> {
    fs::read_to_string(preference_path())
        .ok()
        .and_then(|value| parse_preference(&value))
}

/// Saves a choice the user made by hand. `None` removes it so that later
/// installs and updates detect the network again.
pub fn save_preference(choice: Option<bool>) -> io::Result<()> {
    let path = preference_path();
    match choice {
        Some(enabled) => {
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::write(path, if enabled { "on\n" } else { "off\n" })
        }
        None => match fs::remove_file(path) {
            Err(error) if error.kind() != io::ErrorKind::NotFound => Err(error),
            _ => Ok(()),
        },
    }
}

/// Mirrors are needed when the global probe fails but the domestic one works.
/// If both fail the network is down, and GitHub is as good a default as any.
pub fn decide(global_reachable: bool, china_reachable: bool) -> bool {
    !global_reachable && china_reachable
}

/// Probes both sides in parallel; takes at most `PROBE_TIMEOUT`.
pub fn detect_china_network() -> bool {
    let global_url =
        env::var("SUZENT_GLOBAL_PROBE_URL").unwrap_or_else(|_| GLOBAL_PROBE_URL.to_string());
    let china_url =
        env::var("SUZENT_CHINA_PROBE_URL").unwrap_or_else(|_| CHINA_PROBE_URL.to_string());
    let global = thread::spawn(move || reachable(&global_url));
    let china = reachable(&china_url);
    decide(global.join().unwrap_or(false), china)
}

fn reachable(url: &str) -> bool {
    client(PROBE_TIMEOUT)
        .and_then(|client| client.get(url).send().ok())
        .is_some_and(|response| response.status().as_u16() < 500)
}

fn client(timeout: Duration) -> Option<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .connect_timeout(timeout)
        .timeout(timeout)
        .build()
        .ok()
}

/// Resolves the mode once per process: explicit choice, else detection.
pub fn china_mode(args: &[String]) -> bool {
    *CHINA_MODE.get_or_init(|| {
        let enabled = explicit_preference(args).unwrap_or_else(|| {
            let detected = detect_china_network();
            if detected {
                eprintln!("Mainland China network detected; using domestic mirrors.");
            }
            detected
        });
        let _ = record_region(enabled);
        enabled
    })
}

/// The mode `china_mode` resolved earlier in this process, without probing.
pub fn resolved_china_mode() -> bool {
    CHINA_MODE.get().copied().unwrap_or(false)
}

/// Records the mode the last install or update used, so the backend can skip
/// startup downloads that cannot succeed behind the firewall.
pub fn record_region(china: bool) -> io::Result<()> {
    let path = preference_path().with_file_name(REGION_FILE);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, if china { "china\n" } else { "global\n" })
}

/// Release download bases to try in order.
pub fn release_bases(china: bool, tag: &str) -> Vec<String> {
    if let Ok(base) = env::var("SUZENT_RELEASE_BASE_URL") {
        if !base.trim().is_empty() {
            return vec![base.trim().trim_end_matches('/').to_string()];
        }
    }
    let github = format!("{GITHUB_RELEASE_BASE}/{tag}");
    if china {
        vec![format!("{MIRROR_RELEASE_BASE}/{tag}"), github]
    } else {
        vec![github]
    }
}

/// Downloads `name` from the first release base that serves it.
pub fn fetch_release_file(bases: &[String], name: &str) -> Result<Vec<u8>, String> {
    let client = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .connect_timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("failed to create download client: {error}"))?;
    let mut errors = Vec::new();
    for base in bases {
        let url = format!("{}/{name}", base.trim_end_matches('/'));
        match client
            .get(&url)
            .send()
            .and_then(|response| response.error_for_status())
            .and_then(|response| response.bytes())
        {
            Ok(bytes) => return Ok(bytes.to_vec()),
            Err(error) => errors.push(format!("{url}: {error}")),
        }
    }
    Err(format!("failed to download {name}: {}", errors.join("; ")))
}

/// Latest stable tag. In China mode the mirror listing comes first, so the
/// chosen version is one the mirror can already serve.
pub fn latest_release_tag(china: bool) -> Result<String, String> {
    if let Ok(api) = env::var("SUZENT_LATEST_RELEASE_API") {
        return latest_from_api(&api);
    }
    let mut errors = Vec::new();
    if china {
        match latest_from_mirror() {
            Ok(tag) => return Ok(tag),
            Err(error) => errors.push(error),
        }
    }
    match latest_from_api(LATEST_RELEASE_API) {
        Ok(tag) => return Ok(tag),
        Err(error) => errors.push(error),
    }
    // The unauthenticated API allows 60 requests an hour per IP, which shared
    // addresses exhaust; the release page redirect has no such limit.
    match latest_from_redirect() {
        Ok(tag) => Ok(tag),
        Err(error) => {
            errors.push(error);
            Err(format!(
                "failed to resolve latest release: {}",
                errors.join("; ")
            ))
        }
    }
}

fn latest_from_api(api: &str) -> Result<String, String> {
    #[derive(serde::Deserialize)]
    struct Release {
        tag_name: String,
    }
    client(Duration::from_secs(20))
        .ok_or("failed to create release client")?
        .get(api)
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| format!("release API: {error}"))?
        .json::<Release>()
        .map(|release| release.tag_name)
        .map_err(|error| format!("invalid release API response: {error}"))
}

fn latest_from_redirect() -> Result<String, String> {
    let response = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .timeout(Duration::from_secs(20))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|error| format!("failed to create release client: {error}"))?
        .get(GITHUB_LATEST_RELEASE)
        .send()
        .map_err(|error| format!("release page: {error}"))?;
    let location = response
        .headers()
        .get(reqwest::header::LOCATION)
        .and_then(|value| value.to_str().ok())
        .ok_or("release page did not redirect to a tag")?;
    tag_from_release_url(location).ok_or_else(|| format!("unexpected release redirect: {location}"))
}

pub fn tag_from_release_url(url: &str) -> Option<String> {
    let tag = url.trim_end_matches('/').rsplit('/').next()?;
    is_release_tag(tag).then(|| tag.to_string())
}

fn latest_from_mirror() -> Result<String, String> {
    let listing = client(Duration::from_secs(15))
        .ok_or("failed to create mirror client")?
        .get(format!("{MIRROR_RELEASE_BASE}/"))
        .send()
        .and_then(|response| response.error_for_status())
        .map_err(|error| format!("release mirror: {error}"))?
        .text()
        .map_err(|error| format!("release mirror: {error}"))?;
    latest_tag_in_listing(&listing).ok_or_else(|| "release mirror lists no stable release".into())
}

/// Picks the highest `vX.Y.Z` directory from an npmmirror binary listing.
pub fn latest_tag_in_listing(listing: &str) -> Option<String> {
    let entries: Vec<serde_json::Value> = serde_json::from_str(listing).ok()?;
    entries
        .iter()
        .filter_map(|entry| entry.get("name")?.as_str())
        .map(|name| name.trim_end_matches('/'))
        .filter(|name| is_release_tag(name))
        .max_by_key(|name| version_key(name))
        .map(str::to_string)
}

pub fn is_release_tag(value: &str) -> bool {
    value
        .strip_prefix('v')
        .map(|version| {
            let parts: Vec<&str> = version.split('.').collect();
            parts.len() == 3
                && parts
                    .iter()
                    .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
        })
        .unwrap_or(false)
}

fn version_key(tag: &str) -> Vec<u64> {
    tag.trim_start_matches('v')
        .split('.')
        .map(|part| part.parse().unwrap_or(0))
        .collect()
}

/// Repositories to clone or fetch the source from, in order.
pub fn repo_sources(china: bool) -> Vec<&'static str> {
    if china {
        vec![GITEE_REPO_URL, GITHUB_REPO_URL]
    } else {
        vec![GITHUB_REPO_URL]
    }
}

/// Playwright downloads Chromium from Chrome for Testing everywhere except
/// Linux arm64, where it uses its own builds that the CfT mirror does not have.
const CHROME_FOR_TESTING_BUILDS: bool =
    !(cfg!(target_os = "linux") && cfg!(target_arch = "aarch64"));

/// Environment for child processes in China mode. Values the user already
/// set win.
pub fn apply_mirror_env(command: &mut Command, enabled: bool) {
    if !enabled {
        return;
    }
    for (key, value) in [
        ("UV_DEFAULT_INDEX", PYPI_MIRROR),
        (
            "UV_PYTHON_INSTALL_MIRROR",
            "https://registry.npmmirror.com/-/binary/python-build-standalone",
        ),
        ("NPM_CONFIG_REGISTRY", "https://registry.npmmirror.com"),
        (
            "PLAYWRIGHT_DOWNLOAD_HOST",
            "https://npmmirror.com/mirrors/playwright",
        ),
        // Playwright's Chromium is a Chrome for Testing build with its own URL
        // layout, except on Linux arm64 (see `CHROME_FOR_TESTING_BUILDS`).
        (
            "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
            "https://cdn.npmmirror.com/binaries/chrome-for-testing",
        ),
        (
            "NVM_NODEJS_ORG_MIRROR",
            "https://npmmirror.com/mirrors/node",
        ),
        (
            "RUSTUP_DIST_SERVER",
            "https://mirrors.tuna.tsinghua.edu.cn/rustup",
        ),
        (
            "RUSTUP_UPDATE_ROOT",
            "https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup",
        ),
    ] {
        if key == "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST" && !CHROME_FOR_TESTING_BUILDS {
            continue;
        }
        if env::var(key)
            .ok()
            .filter(|existing| !existing.trim().is_empty())
            .is_none()
        {
            command.env(key, value);
        }
    }
}

/// `uv sync --frozen` downloads every wheel from the URL recorded in uv.lock
/// (files.pythonhosted.org) and ignores `UV_DEFAULT_INDEX`, so China mode
/// installs the same locked, hash-pinned set through the mirror instead.
pub fn sync_locked_dependencies_via_mirror(
    uv: &Path,
    root: &Path,
    extras: &[&str],
    mut run: impl FnMut(&mut Command) -> bool,
) -> bool {
    let requirements = env::temp_dir().join(format!(
        "suzent-requirements-{}-{}.txt",
        std::process::id(),
        extras.join("-")
    ));
    let requirements_arg = requirements.to_string_lossy().to_string();
    let mut export = vec!["export", "--frozen", "--quiet", "-o", &requirements_arg];
    for extra in extras {
        export.extend(["--extra", extra]);
    }
    let steps: [Vec<&str>; 3] = [
        export,
        vec!["venv", "--allow-existing", "--quiet"],
        vec!["pip", "sync", &requirements_arg],
    ];
    let synced = steps.iter().all(|args| {
        let mut command = Command::new(uv);
        command.args(args).current_dir(root);
        apply_mirror_env(&mut command, true);
        run(&mut command)
    });
    let _ = fs::remove_file(&requirements);
    synced
}

/// The platform tag of the uv wheel that runs here.
fn uv_wheel_platform() -> Option<&'static str> {
    if cfg!(all(windows, target_arch = "x86_64")) {
        Some("win_amd64")
    } else if cfg!(all(windows, target_arch = "aarch64")) {
        Some("win_arm64")
    } else if cfg!(all(target_os = "macos", target_arch = "aarch64")) {
        Some("macosx_11_0_arm64")
    } else if cfg!(all(target_os = "macos", target_arch = "x86_64")) {
        Some("macosx_10_12_x86_64")
    } else if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        Some("manylinux_2_17_x86_64")
    } else if cfg!(all(target_os = "linux", target_arch = "aarch64")) {
        Some("manylinux_2_17_aarch64")
    } else {
        None
    }
}

/// Finds the newest uv wheel for `platform` in a PEP 503 project page.
/// Returns the absolute URL with its `#sha256=` fragment.
pub fn newest_uv_wheel(page: &str, page_url: &str, platform: &str) -> Option<String> {
    page.split("href=\"")
        .skip(1)
        .filter_map(|rest| rest.split('"').next())
        .filter_map(|href| {
            let file = href.split('#').next()?.rsplit('/').next()?;
            let version = file.strip_prefix("uv-")?.split('-').next()?;
            let stable = version
                .split('.')
                .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()));
            (stable && file.ends_with(".whl") && file.contains(platform))
                .then(|| (version_key(version), href.replace("&amp;", "&")))
        })
        .max_by(|left, right| left.0.cmp(&right.0))
        .map(|(_, href)| join_url(page_url, &href))
}

fn join_url(base: &str, href: &str) -> String {
    if href.starts_with("http://") || href.starts_with("https://") {
        return href.to_string();
    }
    let origin_end = base
        .find("://")
        .and_then(|scheme| base[scheme + 3..].find('/').map(|path| scheme + 3 + path))
        .unwrap_or(base.len());
    if href.starts_with('/') {
        return format!("{}{href}", &base[..origin_end]);
    }
    let mut prefix = base.to_string();
    if !prefix.ends_with('/') {
        prefix.push('/');
    }
    let mut parts: Vec<&str> = prefix[origin_end..]
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    for segment in href.split('/') {
        match segment {
            ".." => {
                parts.pop();
            }
            "." | "" => {}
            other => parts.push(other),
        }
    }
    format!("{}/{}", &base[..origin_end], parts.join("/"))
}

/// Installs uv from its PyPI wheel on the domestic mirror, since the official
/// installer downloads the binary from GitHub. Returns the installed path.
pub fn install_uv_from_mirror(bin_dir: &Path) -> Result<PathBuf, String> {
    let platform = uv_wheel_platform().ok_or("no uv wheel for this platform")?;
    let page_url = format!("{PYPI_MIRROR}/uv/");
    let http = client(Duration::from_secs(60)).ok_or("failed to create download client")?;
    let page = http
        .get(&page_url)
        .send()
        .and_then(|response| response.error_for_status())
        .and_then(|response| response.text())
        .map_err(|error| format!("failed to list uv on the PyPI mirror: {error}"))?;
    let url = newest_uv_wheel(&page, &page_url, platform)
        .ok_or("the PyPI mirror lists no uv wheel for this platform")?;
    let expected = url
        .split("#sha256=")
        .nth(1)
        .map(str::to_string)
        .ok_or("the PyPI mirror did not publish a checksum for uv")?;
    let download = url.split('#').next().unwrap_or(&url);
    let wheel = reqwest::blocking::Client::builder()
        .user_agent("suzent-installer")
        .connect_timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("failed to create download client: {error}"))?
        .get(download)
        .send()
        .and_then(|response| response.error_for_status())
        .and_then(|response| response.bytes())
        .map_err(|error| format!("failed to download uv: {error}"))?;
    let actual = sha256_hex(&wheel);
    if !actual.eq_ignore_ascii_case(&expected) {
        return Err(format!(
            "uv checksum mismatch: expected {expected}, found {actual}"
        ));
    }
    extract_uv_binaries(&wheel, bin_dir)
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}

/// Copies `uv` and `uvx` out of a wheel's `.data/scripts/` directory.
pub fn extract_uv_binaries(wheel: &[u8], bin_dir: &Path) -> Result<PathBuf, String> {
    let mut archive = zip::ZipArchive::new(io::Cursor::new(wheel))
        .map_err(|error| format!("invalid uv wheel: {error}"))?;
    fs::create_dir_all(bin_dir)
        .map_err(|error| format!("failed to create {}: {error}", bin_dir.display()))?;
    let suffix = if cfg!(windows) { ".exe" } else { "" };
    let mut installed = None;
    for name in ["uv", "uvx"] {
        let file_name = format!("{name}{suffix}");
        let entry_name = archive
            .file_names()
            .filter_map(|name| name.ok().map(|name| name.to_string()))
            .find(|entry| {
                entry.contains(".data/scripts/") && entry.ends_with(&format!("/{file_name}"))
            });
        let Some(entry_name) = entry_name else {
            if name == "uv" {
                return Err("uv wheel does not contain the uv binary".into());
            }
            continue;
        };
        let mut entry = archive
            .by_name(&entry_name)
            .map_err(|error| format!("invalid uv wheel: {error}"))?;
        let mut bytes = Vec::new();
        entry
            .read_to_end(&mut bytes)
            .map_err(|error| format!("failed to read {entry_name}: {error}"))?;
        let destination = bin_dir.join(&file_name);
        let temporary = destination.with_extension("download");
        fs::File::create(&temporary)
            .and_then(|mut file| file.write_all(&bytes))
            .and_then(|_| fs::rename(&temporary, &destination))
            .map_err(|error| format!("failed to install {}: {error}", destination.display()))?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&destination, fs::Permissions::from_mode(0o755)).map_err(
                |error| {
                    format!(
                        "failed to mark {} executable: {error}",
                        destination.display()
                    )
                },
            )?;
        }
        if name == "uv" {
            installed = Some(destination);
        }
    }
    installed.ok_or_else(|| "uv wheel does not contain the uv binary".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn china_mode_clones_from_gitee_before_github() {
        assert_eq!(repo_sources(true), vec![GITEE_REPO_URL, GITHUB_REPO_URL]);
        assert_eq!(repo_sources(false), vec![GITHUB_REPO_URL]);
    }

    #[test]
    fn mirrors_only_when_global_is_blocked_and_china_reachable() {
        assert!(decide(false, true));
        assert!(!decide(true, true));
        assert!(!decide(true, false));
        assert!(!decide(false, false));
    }

    #[test]
    fn parses_preferences() {
        assert_eq!(parse_preference("1"), Some(true));
        assert_eq!(parse_preference(" CN "), Some(true));
        assert_eq!(parse_preference("off"), Some(false));
        assert_eq!(parse_preference("0"), Some(false));
        assert_eq!(parse_preference("auto"), None);
        assert_eq!(parse_preference(""), None);
    }

    #[test]
    fn explicit_flags_win() {
        assert_eq!(explicit_preference(&["--china-mirror".into()]), Some(true));
        assert_eq!(
            explicit_preference(&["--no-china-mirror".into()]),
            Some(false)
        );
    }

    #[test]
    fn picks_highest_stable_tag_from_mirror_listing() {
        let listing = r#"[
            {"id":"1","category":"suzent","name":"v0.9.0/","date":"","type":"dir","url":""},
            {"id":"2","category":"suzent","name":"v0.17.0/","date":"","type":"dir","url":""},
            {"id":"3","category":"suzent","name":"mobile-v0.2.0/","date":"","type":"dir","url":""},
            {"id":"4","category":"suzent","name":"v0.16.3/","date":"","type":"dir","url":""}
        ]"#;
        assert_eq!(latest_tag_in_listing(listing).as_deref(), Some("v0.17.0"));
        assert_eq!(latest_tag_in_listing("[]"), None);
        assert_eq!(latest_tag_in_listing("<html>"), None);
    }

    #[test]
    fn reads_tag_from_release_redirect() {
        assert_eq!(
            tag_from_release_url("https://github.com/cyzus/suzent/releases/tag/v0.17.0").as_deref(),
            Some("v0.17.0")
        );
        assert_eq!(
            tag_from_release_url("https://github.com/cyzus/suzent/releases"),
            None
        );
    }

    #[test]
    fn china_release_bases_try_mirror_then_github() {
        if env::var("SUZENT_RELEASE_BASE_URL").is_ok() {
            return;
        }
        assert_eq!(
            release_bases(true, "v1.2.3"),
            vec![
                "https://registry.npmmirror.com/-/binary/suzent/v1.2.3".to_string(),
                "https://github.com/cyzus/suzent/releases/download/v1.2.3".to_string(),
            ]
        );
        assert_eq!(
            release_bases(false, "v1.2.3"),
            vec!["https://github.com/cyzus/suzent/releases/download/v1.2.3".to_string()]
        );
    }

    #[test]
    fn finds_newest_uv_wheel_for_platform() {
        let page = r#"<html><body>
            <a href="../../packages/aa/uv-0.9.9-py3-none-win_amd64.whl#sha256=111">uv-0.9.9-py3-none-win_amd64.whl</a>
            <a href="../../packages/bb/uv-0.10.2-py3-none-win_amd64.whl#sha256=222">uv-0.10.2-py3-none-win_amd64.whl</a>
            <a href="../../packages/cc/uv-0.10.2-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl#sha256=333">x</a>
            <a href="../../packages/dd/uv-0.11.0rc1-py3-none-win_amd64.whl#sha256=444">x</a>
            <a href="../../packages/ee/uv-0.10.2.tar.gz#sha256=555">x</a>
        </body></html>"#;
        assert_eq!(
            newest_uv_wheel(page, "https://pypi.tuna.tsinghua.edu.cn/simple/uv/", "win_amd64").as_deref(),
            Some("https://pypi.tuna.tsinghua.edu.cn/packages/bb/uv-0.10.2-py3-none-win_amd64.whl#sha256=222")
        );
        assert_eq!(
            newest_uv_wheel(page, "https://pypi.tuna.tsinghua.edu.cn/simple/uv/", "manylinux_2_17_x86_64").as_deref(),
            Some("https://pypi.tuna.tsinghua.edu.cn/packages/cc/uv-0.10.2-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl#sha256=333")
        );
        assert_eq!(
            newest_uv_wheel(page, "https://example.com/simple/uv/", "macosx_11_0_arm64"),
            None
        );
    }

    #[test]
    fn joins_absolute_and_relative_links() {
        assert_eq!(
            join_url(
                "https://m.example/simple/uv/",
                "https://files.example/uv.whl"
            ),
            "https://files.example/uv.whl"
        );
        assert_eq!(
            join_url("https://m.example/simple/uv/", "/packages/uv.whl"),
            "https://m.example/packages/uv.whl"
        );
    }

    #[test]
    fn extracts_uv_from_wheel() {
        let mut buffer = io::Cursor::new(Vec::new());
        {
            let mut writer = zip::ZipWriter::new(&mut buffer);
            let options = zip::write::SimpleFileOptions::default();
            let suffix = if cfg!(windows) { ".exe" } else { "" };
            writer
                .start_file(format!("uv-0.10.2.data/scripts/uv{suffix}"), options)
                .unwrap();
            writer.write_all(b"uv-binary").unwrap();
            writer
                .start_file(format!("uv-0.10.2.data/scripts/uvx{suffix}"), options)
                .unwrap();
            writer.write_all(b"uvx-binary").unwrap();
            writer.start_file("uv/__init__.py", options).unwrap();
            writer.finish().unwrap();
        }
        let temp = tempfile::tempdir().unwrap();
        let installed = extract_uv_binaries(buffer.get_ref(), temp.path()).unwrap();
        assert_eq!(fs::read(&installed).unwrap(), b"uv-binary");
        let uvx = temp
            .path()
            .join(if cfg!(windows) { "uvx.exe" } else { "uvx" });
        assert_eq!(fs::read(uvx).unwrap(), b"uvx-binary");
    }
}
