#!/usr/bin/env bash
# SUZENT Setup & Update Script
# Usage:
#   Fresh install:  curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
#   Update:         suzent update   (or re-run this script inside the repo)
#   Flags (env):    SUZENT_DIR=~/suzent  SUZENT_BRANCH=main  SUZENT_SKIP_PLAYWRIGHT=1
#                   SUZENT_CHINA_MIRROR=1  SUZENT_REPO_URL=...  SUZENT_RELEASE_BASE_URL=...

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
RELEASE_BASE_URL="${SUZENT_RELEASE_BASE_URL:-https://github.com/cyzus/suzent/releases/latest/download}"
SUZENT_DIR="${SUZENT_DIR:-$HOME/suzent}"
SUZENT_BRANCH="${SUZENT_BRANCH:-main}"
CHINA_MIRROR="${SUZENT_CHINA_MIRROR:-0}"
MIN_NODE_MAJOR=20

enable_china_mirrors() {
    case "$CHINA_MIRROR" in
        1|true|TRUE|yes|YES|cn|CN) ;;
        *) return ;;
    esac

    export UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
    export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"
    export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}"
    export NVM_NODEJS_ORG_MIRROR="${NVM_NODEJS_ORG_MIRROR:-https://npmmirror.com/mirrors/node}"
    export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://mirrors.tuna.tsinghua.edu.cn/rustup}"
    export RUSTUP_UPDATE_ROOT="${RUSTUP_UPDATE_ROOT:-https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup}"
    info "China mirror mode enabled for PyPI, npm, Playwright, Node, and Rustup."
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

# ── Check: git ────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    die "git is required. Install it and re-run."
fi
ok "git $(git --version | awk '{print $3}')"

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

if ! check_node; then
    install_node
    check_node || die "Node.js installation failed. Install v${MIN_NODE_MAJOR}+ from https://nodejs.org/ and re-run."
fi

# ── Check/install: uv ────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    info "Installing uv..."
    curl -LsSf "$UV_INSTALL_URL" | sh
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
if [ "$IS_UPDATE" = true ]; then
    info "Updating SUZENT in $SUZENT_DIR..."
    cd "$SUZENT_DIR"

    # Stash local changes before pulling
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Stashing local changes..."
        git stash push -m "suzent-update-$(date +%Y%m%d-%H%M%S)"
    fi

    git fetch "$UPDATE_REMOTE" "$SUZENT_BRANCH"
    git checkout "$SUZENT_BRANCH" 2>/dev/null || true
    git pull "$UPDATE_REMOTE" "$SUZENT_BRANCH"
    ok "Repository updated to $(git rev-parse --short HEAD)"
else
    if [ -d "$SUZENT_DIR" ]; then
        die "Directory $SUZENT_DIR already exists but is not a git repo. Remove it or set SUZENT_DIR to a different path."
    fi
    info "Cloning SUZENT into $SUZENT_DIR..."
    git clone --branch "$SUZENT_BRANCH" "$REPO_URL" "$SUZENT_DIR"
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
info "Syncing Python dependencies with social channel support (uv sync --frozen --extra social)..."
uv sync --frozen --extra social || die "uv sync --frozen --extra social failed — check errors above."
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
    local url tmp
    url="${RELEASE_BASE_URL%/}/$asset"
    tmp="bin/suzent-ui.tmp"

    info "Downloading pre-built UI binary..."
    if ! curl --connect-timeout 15 --max-time 300 -fL "$url" -o "$tmp"; then
        rm -f "$tmp"
        warn "UI binary download failed. Retry later, or set SUZENT_DEV_SETUP=1 for developer dependencies."
        return 1
    fi

    mv "$tmp" "bin/suzent-ui"
    chmod +x "bin/suzent-ui"
    echo "latest" > "bin/version.txt"
    ok "UI binary ready (bin/suzent-ui)"
}
download_binary || true

install_dev_deps() {
    ensure_rust

    info "Installing frontend dependencies (npm install)..."
    (cd frontend && npm install) || die "npm install failed in frontend/."
    ok "Frontend dependencies ready"

    info "Installing src-tauri dependencies (npm install)..."
    (cd src-tauri && npm install) || die "npm install failed in src-tauri/."
    ok "Tauri JS dependencies ready"
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
ok "Workspace marked as bootstrapped"

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
    echo -e "  ${YELLOW}Next:${RESET} edit ${CYAN}$SUZENT_DIR/.env${RESET} with your API keys, then run:"
    echo -e "  ${CYAN}suzent start${RESET}"
    echo ""
    echo -e "  If 'suzent' is not found, restart your terminal or run:"
    echo -e "  ${CYAN}source ~/.bashrc${RESET}  (or ~/.zshrc)"
fi
echo ""
