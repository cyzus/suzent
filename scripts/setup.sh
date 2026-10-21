#!/usr/bin/env bash
# SUZENT Setup & Update Script
# Usage:
#   Fresh install:  curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
#   Update:         suzent update   (or re-run this script inside the repo)
#   Flags (env):    SUZENT_DIR=~/suzent  SUZENT_BRANCH=main  SUZENT_SKIP_PLAYWRIGHT=1
#                   SUZENT_CHINA_MIRROR=1|0 (default: detect from the network)
#                   SUZENT_REPO_URL=...  SUZENT_RELEASE_BASE_URL=...

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info() { echo -e "${CYAN}[*]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
die()  { echo -e "${RED}[✗]${RESET} $*"; exit 1; }

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="${SUZENT_REPO_URL:-https://github.com/cyzus/suzent.git}"
UPDATE_REMOTE="${SUZENT_REPO_URL:-origin}"
UV_INSTALL_URL="${SUZENT_UV_INSTALL_URL:-https://astral.sh/uv/install.sh}"
NVM_INSTALL_URL="${SUZENT_NVM_INSTALL_URL:-https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh}"
RELEASE_BASE_URL="${SUZENT_RELEASE_BASE_URL:-}"
SUZENT_DIR="${SUZENT_DIR:-$HOME/suzent}"
SUZENT_BRANCH_EXPLICIT="${SUZENT_BRANCH+x}"
SUZENT_BRANCH="${SUZENT_BRANCH:-main}"
MIN_NODE_MAJOR=20
STATE_DIR="$HOME/.suzent"
MIRROR_RELEASE_BASE="https://registry.npmmirror.com/-/binary/suzent"
GITHUB_RELEASE_BASE="https://github.com/cyzus/suzent/releases/download"
PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

# on/off from a flag value; anything else (including "auto") means detect.
parse_mirror_choice() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')" in
        1|true|yes|on|cn|china) echo 1 ;;
        0|false|no|off|global) echo 0 ;;
        *) echo "" ;;
    esac
}

# Mirrors are needed when a global endpoint is unreachable but a domestic one
# answers -- i.e. the network this machine is on, not its language.
detect_china_network() {
    if curl -fsS -o /dev/null --connect-timeout 4 --max-time 4 https://www.google.com/generate_204 2>/dev/null; then
        echo 0
    elif curl -sS -o /dev/null --connect-timeout 4 --max-time 4 https://registry.npmmirror.com/ 2>/dev/null; then
        echo 1
    else
        echo 0
    fi
}

CHINA_MIRROR="$(parse_mirror_choice "${SUZENT_CHINA_MIRROR:-}")"
[ -n "$CHINA_MIRROR" ] || CHINA_MIRROR="$(parse_mirror_choice "$(cat "$STATE_DIR/china-mirror" 2>/dev/null)")"
CHINA_MIRROR_DETECTED=false
if [ -z "$CHINA_MIRROR" ]; then
    CHINA_MIRROR="$(detect_china_network)"
    CHINA_MIRROR_DETECTED=true
fi

china_mirror_enabled() {
    [ "$CHINA_MIRROR" = "1" ]
}

enable_china_mirrors() {
    mkdir -p "$STATE_DIR"
    # Read by the backend and `suzent update` (see suzent/network_region.py).
    if china_mirror_enabled; then echo china; else echo global; fi > "$STATE_DIR/network-region"
    china_mirror_enabled || return 0
    if [ "$CHINA_MIRROR_DETECTED" = true ]; then
        info "Mainland China network detected. Set SUZENT_CHINA_MIRROR=0 to use the default sources."
    fi

    export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    export UV_PYTHON_INSTALL_MIRROR="${UV_PYTHON_INSTALL_MIRROR:-https://registry.npmmirror.com/-/binary/python-build-standalone}"
    export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"
    export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}"
    # Playwright's Chromium is a Chrome for Testing build with its own URL
    # layout, except on Linux arm64 where Playwright ships its own builds.
    if [ "$(uname -s)-$(uname -m)" != "Linux-aarch64" ]; then
      export PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST="${PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST:-https://cdn.npmmirror.com/binaries/chrome-for-testing}"
    fi
    export NVM_NODEJS_ORG_MIRROR="${NVM_NODEJS_ORG_MIRROR:-https://npmmirror.com/mirrors/node}"
    export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://mirrors.tuna.tsinghua.edu.cn/rustup}"
    export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup}"
    info "China mirror mode enabled for Python, PyPI, npm, Playwright, Node, and Rustup."
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}  ███████╗██╗   ██╗███████╗███████╗███╗   ██╗████████╗${RESET}"
echo -e "${CYAN}  ██╔════╝██║   ██║╚══███╔╝██╔════╝████╗  ██║╚══██╔══╝${RESET}"
echo -e "${CYAN}  ███████╗██║   ██║  ███╔╝ █████╗  ██╔██╗ ██║   ██║   ${RESET}"
echo -e "${CYAN}  ╚════██║██║   ██║ ███╔╝  ██╔══╝  ██║╚██╗██║   ██║   ${RESET}"
echo -e "${CYAN}  ███████║╚██████╔╝███████╗███████╗██║ ╚████║   ██║   ${RESET}"
echo -e "${CYAN}  ╚══════╝ ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ${RESET}"
echo ""

# ── Detect if this is an update or fresh install ──────────────────────────────
IS_UPDATE=false
if [ -d "$SUZENT_DIR/.git" ]; then
    IS_UPDATE=true
fi

# ── OS detection ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Darwin) OS_NAME="macOS" ;;
    Linux)  OS_NAME="Linux" ;;
    *)      die "Unsupported OS: $OS" ;;
esac
ok "$OS_NAME detected"
enable_china_mirrors

INSTALL_REF="$SUZENT_BRANCH"
RELEASE_TAG=""
if [ -z "$SUZENT_BRANCH_EXPLICIT" ] && [ "${SUZENT_DEV_SETUP:-0}" != "1" ]; then
    RELEASE_TAG="${SUZENT_RELEASE_TAG:-}"
    if [ -z "$RELEASE_TAG" ]; then
        info "Resolving latest stable release..."
        # The mirror first in China mode, so the version is one it can serve.
        if china_mirror_enabled; then
            RELEASE_TAG="$(curl -fsSL --max-time 15 "$MIRROR_RELEASE_BASE/" 2>/dev/null \
                | grep -oE '"name": *"v[0-9]+\.[0-9]+\.[0-9]+/"' \
                | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' \
                | sort -t. -k1.2,1n -k2,2n -k3,3n | tail -n 1 || true)"
        fi
        if [ -z "$RELEASE_TAG" ]; then
            release_url="$(curl -fsSL -o /dev/null -w '%{url_effective}' \
                https://github.com/cyzus/suzent/releases/latest)" \
                || die "Could not resolve the latest stable release."
            RELEASE_TAG="${release_url##*/}"
        fi
    fi
    [[ "$RELEASE_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] \
        || die "Invalid stable release tag: $RELEASE_TAG"
    INSTALL_REF="$RELEASE_TAG"
    info "Installing matched stable release $RELEASE_TAG"
fi

# Release download sources in the order to try them.
if [ -n "$RELEASE_BASE_URL" ]; then
    RELEASE_BASES=("${RELEASE_BASE_URL%/}")
elif [ -z "$RELEASE_TAG" ]; then
    RELEASE_BASES=("https://github.com/cyzus/suzent/releases/latest/download")
elif china_mirror_enabled; then
    RELEASE_BASES=("$MIRROR_RELEASE_BASE/$RELEASE_TAG" "$GITHUB_RELEASE_BASE/$RELEASE_TAG")
else
    RELEASE_BASES=("$GITHUB_RELEASE_BASE/$RELEASE_TAG")
fi

# ── Helper: refresh PATH after install ───────────────────────────────────────
refresh_path() {
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    # Also source uv env if present
    [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env" 2>/dev/null || true
    [ -f "$HOME/.local/share/uv/env" ] && source "$HOME/.local/share/uv/env" 2>/dev/null || true
}

# ── Helper: add dir to shell config ──────────────────────────────────────────
add_to_path_config() {
    local dir="$1"
    [[ ":$PATH:" == *":$dir:"* ]] && return
    local cfg
    case "$(basename "${SHELL:-bash}")" in
        zsh)  cfg="$HOME/.zshrc" ;;
        fish) cfg="$HOME/.config/fish/config.fish" ;;
        *)    cfg="${HOME}/.bashrc" ;;
    esac
    if [ -f "$cfg" ] && grep -q "$dir" "$cfg" 2>/dev/null; then
        return
    fi
    echo "" >> "$cfg"
    echo "export PATH=\"$dir:\$PATH\"" >> "$cfg"
    warn "Added $dir to PATH in $cfg — run: source $cfg"
}

# ── Helper: verified release downloads ──────────────────────────────────────
sha256_of() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# download_release_asset <asset> <destination>: tries each release source in
# turn and keeps the first download that matches the release's SHA256SUMS, so
# a mirror can make a download faster but never different.
download_release_asset() {
    local asset="$1" dest="$2" base sums expected actual tmp
    tmp="$dest.download"
    for base in "${RELEASE_BASES[@]}"; do
        sums="$(curl -fsSL --connect-timeout 15 --max-time 60 "$base/SHA256SUMS" 2>/dev/null || true)"
        expected="$(printf '%s\n' "$sums" | awk -v name="$asset" '{ file = $2; sub(/^\*/, "", file) } file == name { print tolower($1); exit }')"
        if [ -n "$RELEASE_TAG" ] && [ -z "$expected" ]; then
            warn "No checksum for $asset at $base; trying the next source."
            continue
        fi
        if ! curl --connect-timeout 15 --max-time 300 -fL "$base/$asset" -o "$tmp"; then
            warn "Download from $base failed; trying the next source."
            continue
        fi
        actual="$(sha256_of "$tmp")"
        if [ -n "$expected" ] && [ -n "$actual" ] && [ "$actual" != "$expected" ]; then
            warn "Checksum mismatch for $asset from $base; trying the next source."
            continue
        fi
        mv "$tmp" "$dest"
        return 0
    done
    rm -f "$tmp"
    return 1
}

# ── Helper: uv from the PyPI mirror ──────────────────────────────────────────
# The official uv installer downloads the binary from GitHub. uv is also
# published as a wheel on PyPI, which the Tsinghua mirror serves domestically.
install_uv_from_mirror() {
    local platform page href url expected tmp wheel version
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) platform="macosx_11_0_arm64" ;;
        Darwin-x86_64) platform="macosx_10_12_x86_64" ;;
        Linux-x86_64) platform="manylinux_2_17_x86_64" ;;
        Linux-aarch64|Linux-arm64) platform="manylinux_2_17_aarch64" ;;
        *) return 1 ;;
    esac
    page="$(curl -fsSL --max-time 30 "$PYPI_MIRROR/uv/")" || return 1
    href="$(printf '%s' "$page" | grep -oE 'href="[^"]*uv-[0-9]+\.[0-9]+\.[0-9]+-[^"]*'"$platform"'[^"]*\.whl#sha256=[0-9a-f]+' \
        | sed 's/^href="//' \
        | awk -F'uv-' '{ split($NF, v, "-"); print v[1] "\t" $0 }' \
        | sort -t. -k1,1n -k2,2n -k3,3n | tail -n 1 | cut -f2-)"
    [ -n "$href" ] || return 1
    expected="${href##*#sha256=}"
    case "$href" in
        http*) url="${href%%#*}" ;;
        /*) url="$(printf '%s' "$PYPI_MIRROR" | grep -oE '^https?://[^/]+')${href%%#*}" ;;
        *) url="$PYPI_MIRROR/uv/${href%%#*}" ;;
    esac
    tmp="$(mktemp -d)"
    wheel="$tmp/uv.whl"
    if ! curl -fsSL --max-time 300 "$url" -o "$wheel" \
        || [ "$(sha256_of "$wheel")" != "$expected" ]; then
        rm -rf "$tmp"
        return 1
    fi
    version="$(basename "${url}" | cut -d- -f2)"
    if command -v unzip &>/dev/null; then
        unzip -q -o "$wheel" "uv-$version.data/scripts/*" -d "$tmp" || { rm -rf "$tmp"; return 1; }
    elif command -v python3 &>/dev/null; then
        python3 -m zipfile -e "$wheel" "$tmp" || { rm -rf "$tmp"; return 1; }
    else
        rm -rf "$tmp"
        return 1
    fi
    mkdir -p "$HOME/.local/bin"
    install -m 755 "$tmp/uv-$version.data/scripts/uv" "$HOME/.local/bin/uv" || { rm -rf "$tmp"; return 1; }
    [ -f "$tmp/uv-$version.data/scripts/uvx" ] && install -m 755 "$tmp/uv-$version.data/scripts/uvx" "$HOME/.local/bin/uvx"
    rm -rf "$tmp"
    export PATH="$HOME/.local/bin:$PATH"
}

# ── Check: git ────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    die "git is required. Install it and re-run."
fi
ok "git $(git --version | awk '{print $3}')"

# ── Optional accelerator: ripgrep ────────────────────────────────────────────
if command -v rg &>/dev/null; then
    ok "ripgrep $(rg --version | awk 'NR==1 {print $2}')"
elif [ "$OS" = "Darwin" ] && command -v brew &>/dev/null; then
    info "Installing optional ripgrep search accelerator..."
    brew install ripgrep || warn "ripgrep install failed — grep_search will use its Python fallback."
elif [ "$(id -u)" -eq 0 ] && command -v apt-get &>/dev/null; then
    info "Installing optional ripgrep search accelerator..."
    apt-get update && apt-get install -y ripgrep || warn "ripgrep install failed — grep_search will use its Python fallback."
else
    warn "ripgrep not found — grep_search will use its Python fallback."
fi

# ── Check/install: Node.js ────────────────────────────────────────────────────
install_node() {
    info "Installing Node.js via nvm..."
    if ! command -v curl &>/dev/null; then
        die "curl is required to install nvm. Please install curl first."
    fi
    export NVM_DIR="$HOME/.nvm"
    curl -fsSL "$NVM_INSTALL_URL" | bash
    # shellcheck source=/dev/null
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    nvm install --lts
    nvm use --lts
}

check_node() {
    if command -v node &>/dev/null; then
        local ver major
        ver="$(node --version | tr -d 'v')"
        major="${ver%%.*}"
        if [ "$major" -ge "$MIN_NODE_MAJOR" ] 2>/dev/null; then
            ok "Node.js v$ver"
            return 0
        else
            warn "Node.js v$ver found but v${MIN_NODE_MAJOR}+ required"
            return 1
        fi
    fi
    return 1
}

# Normal installs only need Node.js for optional coding-agent integrations
# (they run through npx), so a failed install is a warning there.
if ! check_node; then
    install_node || true
    if ! check_node; then
        [ "${SUZENT_DEV_SETUP:-0}" = "1" ] \
            && die "Node.js installation failed. Install v${MIN_NODE_MAJOR}+ from https://nodejs.org/ and re-run."
        warn "Node.js v${MIN_NODE_MAJOR}+ is not installed. Suzent works without it; install it from https://nodejs.org/ (or https://npmmirror.com/mirrors/node/) to use coding-agent integrations."
    fi
fi

# ── Check/install: uv ────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    if china_mirror_enabled && install_uv_from_mirror; then
        ok "uv installed from the PyPI mirror"
    else
        china_mirror_enabled && warn "uv mirror install failed; trying the official installer."
        info "Installing uv..."
        curl -LsSf "$UV_INSTALL_URL" | sh
    fi
    refresh_path
fi
command -v uv &>/dev/null || die "uv installation failed. See https://docs.astral.sh/uv/"
ok "uv $(uv --version | awk '{print $2}')"

ensure_rust() {
    if command -v cargo &>/dev/null; then
        ok "Rust/Cargo $(cargo --version | awk '{print $2}')"
        return
    fi

    if [ -x "$HOME/.cargo/bin/cargo" ]; then
        refresh_path
        if command -v cargo &>/dev/null; then
            ok "Rust/Cargo $(cargo --version | awk '{print $2}')"
            return
        fi
    fi

    info "Installing Rustup/Cargo for developer mode..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    refresh_path
    command -v cargo &>/dev/null || die "Rust installation failed. Restart your shell and re-run."
    ok "Rust/Cargo $(cargo --version | awk '{print $2}')"
}

# ── macOS: Xcode CLI tools ────────────────────────────────────────────────────
if [ "$OS" = "Darwin" ]; then
    if ! xcode-select -p &>/dev/null; then
        info "Installing Xcode Command Line Tools..."
        xcode-select --install 2>/dev/null || true
        die "Please complete the Xcode Tools installation dialog and re-run this script."
    fi
    ok "Xcode Command Line Tools"
fi

# ── Clone or update repo ──────────────────────────────────────────────────────
# China mode clones from the Gitee mirror first and falls back to GitHub.
MIRROR_REPOS=()
if [ -z "${SUZENT_REPO_URL:-}" ] && china_mirror_enabled; then
    MIRROR_REPOS=("https://gitee.com/cyzus/suzent.git")
fi

if [ "$IS_UPDATE" = true ]; then
    info "Updating SUZENT in $SUZENT_DIR..."
    cd "$SUZENT_DIR"

    # Stash local changes before pulling
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Stashing local changes..."
        git stash push -m "suzent-update-$(date +%Y%m%d-%H%M%S)"
    fi

    if [ -n "$RELEASE_TAG" ]; then
        fetched=false
        for remote in "$UPDATE_REMOTE" ${MIRROR_REPOS[@]+"${MIRROR_REPOS[@]}"} "$REPO_URL"; do
            if git fetch "$remote" tag "$INSTALL_REF"; then fetched=true; break; fi
        done
        [ "$fetched" = true ] || die "Could not fetch $INSTALL_REF - check the network and re-run."
        git checkout --detach "$INSTALL_REF"
    else
        git fetch "$UPDATE_REMOTE" "$INSTALL_REF"
        git checkout "$INSTALL_REF" 2>/dev/null || true
        git pull "$UPDATE_REMOTE" "$INSTALL_REF"
    fi
    ok "Repository updated to $(git rev-parse --short HEAD)"
else
    if [ -d "$SUZENT_DIR" ]; then
        die "Directory $SUZENT_DIR already exists but is not a git repo. Remove it or set SUZENT_DIR to a different path."
    fi
    info "Cloning SUZENT into $SUZENT_DIR..."
    # Only developers need the history. Skipping it cuts the download from
    # ~130k objects to ~18 MB, and later fast-forward updates still work.
    clone_depth=(--depth 1)
    [ "${SUZENT_DEV_SETUP:-0}" = "1" ] && clone_depth=()
    cloned=false
    for source in ${MIRROR_REPOS[@]+"${MIRROR_REPOS[@]}"} "$REPO_URL"; do
        info "Cloning from $source"
        if git clone ${clone_depth[@]+"${clone_depth[@]}"} --branch "$INSTALL_REF" "$source" "$SUZENT_DIR"; then
            cloned=true
            break
        fi
    done
    [ "$cloned" = true ] || die "git clone failed - check the network and re-run."
    ok "Repository cloned"
    cd "$SUZENT_DIR"
fi

# We must be in the repo dir from here on
cd "$SUZENT_DIR"

# ── Setup .env ────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        warn "Created .env from template — edit it with your API keys before starting."
    fi
else
    ok ".env already exists"
fi

# ── Install / sync Python dependencies ───────────────────────────────────────
# uv sync --frozen downloads every wheel from the URL recorded in uv.lock
# (files.pythonhosted.org) and ignores UV_DEFAULT_INDEX, so in mirror mode the
# same locked, hash-pinned set is installed through the mirror instead.
sync_python_deps_via_mirror() {
    local requirements status
    requirements="$(mktemp)"
    uv export --frozen --extra social --quiet -o "$requirements" \
        && uv venv --allow-existing --quiet \
        && uv pip sync "$requirements"
    status=$?
    rm -f "$requirements"
    return $status
}

if china_mirror_enabled; then
    info "Syncing Python dependencies with social channel support through the PyPI mirror..."
    sync_python_deps_via_mirror || die "Python dependency install failed — check errors above."
else
    info "Syncing Python dependencies with social channel support (uv sync --frozen --extra social)..."
    uv sync --frozen --extra social || die "uv sync --frozen --extra social failed — check errors above."
fi
ok "Python dependencies ready"

# ── Download pre-built UI binary ─────────────────────────────────────────────
download_binary() {
    local machine
    machine="$(uname -m)"
    local asset
    case "$OS" in
        Darwin)
            [ "$machine" = "arm64" ] && asset="suzent-macos-aarch64" || asset="suzent-macos-x86_64"
            ;;
        Linux)
            asset="suzent-linux-x86_64"
            ;;
        *) return ;;
    esac

    mkdir -p bin
    info "Downloading pre-built UI binary..."
    if ! download_release_asset "$asset" "bin/suzent-ui"; then
        warn "UI binary download failed. Retry later, or set SUZENT_DEV_SETUP=1 for developer dependencies."
        return 1
    fi
    chmod +x "bin/suzent-ui"
    echo "${RELEASE_TAG:-latest}" > "bin/version.txt"
    ok "UI binary ready (bin/suzent-ui)"
}
download_binary || true

download_updater() {
    local machine asset
    machine="$(uname -m)"
    case "$OS" in
        Darwin)
            [ "$machine" = "arm64" ] && asset="suzent-installer-macos-aarch64" || asset="suzent-installer-macos-x86_64"
            ;;
        Linux)
            asset="suzent-installer-linux-x86_64"
            ;;
        *) return ;;
    esac

    local updater_dir dest
    updater_dir="$HOME/.suzent/updater"
    dest="$updater_dir/suzent-installer"
    mkdir -p "$updater_dir"
    info "Downloading standalone updater..."
    if ! download_release_asset "$asset" "$dest"; then
        warn "Standalone updater download failed. The next 'suzent update' will retry automatically."
        return 1
    fi
    chmod +x "$dest"
    echo "${RELEASE_TAG:-latest}" > "$updater_dir/version.txt"
    ok "Standalone updater ready ($dest)"
}
download_updater || true

# ── Download pre-built web UI ────────────────────────────────────────────────
# `suzent web` serves src/suzent/webui/, which is built from frontend/ with
# Node. A normal install has no Node, so it takes the bundle that release CI
# built from this same tag. Developer setup builds its own below instead.
download_webui() {
    [ -n "$RELEASE_TAG" ] || return 0
    local archive py
    archive="$(mktemp)"
    info "Downloading pre-built web UI..."
    if ! download_release_asset "suzent-webui.zip" "$archive"; then
        rm -f "$archive"
        warn "Web UI download failed. 'suzent web' has no page to serve until the next update."
        return 1
    fi
    py=".venv/bin/python"
    [ -x "$py" ] || py="uv run python"
    if $py scripts/build_webui.py --install-archive "$archive"; then
        ok "Web UI ready (suzent web)"
    else
        warn "Web UI archive could not be unpacked (non-fatal)."
    fi
    rm -f "$archive"
}
[ "${SUZENT_DEV_SETUP:-0}" = "1" ] || download_webui || true

install_dev_deps() {
    ensure_rust

    info "Installing frontend dependencies (npm install)..."
    (cd frontend && npm install) || die "npm install failed in frontend/."
    ok "Frontend dependencies ready"

    info "Installing src-tauri dependencies (npm install)..."
    (cd src-tauri && npm install) || die "npm install failed in src-tauri/."
    ok "Tauri JS dependencies ready"

    # `suzent web` serves the SPA out of src/suzent/webui/, which is a build
    # artifact rather than source. Nothing else in this script produces it, so
    # without this step the command reports "no web UI is built".
    info "Building the web UI bundle (scripts/build_webui.py)..."
    if uv run python scripts/build_webui.py; then
        ok "Web UI bundle staged"
    else
        warn "Web UI build failed -- 'suzent web' will report no bundle (non-fatal)."
    fi
}

if [ "${SUZENT_DEV_SETUP:-0}" = "1" ]; then
    install_dev_deps
else
    info "Skipping frontend/Tauri npm dependencies for normal user setup."
    info "Set SUZENT_DEV_SETUP=1 before running setup to prepare developer mode."
fi

# ── Playwright Chromium ───────────────────────────────────────────────────────
if [ "${SUZENT_SKIP_PLAYWRIGHT:-0}" != "1" ]; then
    info "Installing Playwright Chromium (for web browsing tool)..."
    if [ -x ".venv/bin/playwright" ]; then
        .venv/bin/playwright install chromium || warn "Playwright install failed — web browsing may not work (non-fatal)."
    else
        uv run playwright install chromium || warn "Playwright install failed — web browsing may not work (non-fatal)."
    fi
fi

# ── Global CLI shim ───────────────────────────────────────────────────────────
INSTALL_BIN="$HOME/.local/bin"
SHIM="$INSTALL_BIN/suzent"
mkdir -p "$INSTALL_BIN"

cat > "$SHIM" <<EOF
#!/usr/bin/env bash
# SUZENT CLI shim — auto-generated by setup.sh
[ -f "\$HOME/.cargo/env" ] && source "\$HOME/.cargo/env" 2>/dev/null || true
cd "$SUZENT_DIR"
exec uv run suzent "\$@"
EOF
chmod +x "$SHIM"
ok "CLI shim written to $SHIM"

# ── Bootstrap marker ──────────────────────────────────────────────────────────
# The pre-built UI binary refuses to launch unless the workspace is marked as
# bootstrapped (see is_workspace_bootstrapped in src-tauri). The Rust installer
# writes this; the bash path must do the same or `suzent start` shows the setup
# screen and fails with "installer helper was not found". protocol=1 matches
# PROTOCOL_VERSION in apps/suzent-installer.
printf 'protocol=1\n' > "$SUZENT_DIR/.suzent-bootstrap-complete"
mkdir -p "$SUZENT_DIR/.suzent"
printf '%s' "$([ -n "$RELEASE_TAG" ] && printf stable || printf dev)" \
    > "$SUZENT_DIR/.suzent/update-channel"
# `suzent web` and `suzent repair` read the installed release from here.
if [ -n "$RELEASE_TAG" ]; then
    printf '%s' "$RELEASE_TAG" > "$SUZENT_DIR/.suzent/release-tag"
else
    rm -f "$SUZENT_DIR/.suzent/release-tag"
fi
ok "Workspace marked as bootstrapped"

# ── Launcher shortcuts ────────────────────────────────────────────────────────
# suzent.cli.shortcuts is the same module the Rust installer and the standalone
# updater call, so a CLI install or update creates — and repairs — exactly the
# same launcher entries as the graphical installer.
info "Creating launcher shortcuts..."
if [ -x ".venv/bin/python" ]; then
    .venv/bin/python -m suzent.cli shortcuts \
        || warn "Launcher shortcut setup failed — run 'suzent shortcuts' to retry (non-fatal)."
else
    uv run suzent shortcuts \
        || warn "Launcher shortcut setup failed — run 'suzent shortcuts' to retry (non-fatal)."
fi

add_to_path_config "$INSTALL_BIN"
refresh_path

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
if [ "$IS_UPDATE" = true ]; then
    ok "SUZENT updated successfully!"
    echo ""
    echo -e "  Run ${CYAN}suzent start${RESET} to launch."
else
    ok "SUZENT installed successfully!"
    echo ""
    echo -e "  ${YELLOW}Next:${RESET} run ${CYAN}suzent start${RESET} and add a model provider in the setup screen."
    echo ""
    echo -e "  If 'suzent' is not found, restart your terminal or run:"
    echo -e "  ${CYAN}source ~/.bashrc${RESET}  (or ~/.zshrc)"
fi
echo ""
