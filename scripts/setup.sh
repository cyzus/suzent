#!/usr/bin/env bash
# SUZENT Setup & Update Script
# Usage:
#   Fresh install:  curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
#   Update:         suzent update   (or re-run this script inside the repo)
#   Flags (env):    SUZENT_DIR=~/suzent  SUZENT_BRANCH=main  SUZENT_SKIP_PLAYWRIGHT=1

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
info() { echo -e "${CYAN}[*]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
die()  { echo -e "${RED}[✗]${RESET} $*"; exit 1; }

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/cyzus/suzent.git"
SUZENT_DIR="${SUZENT_DIR:-$HOME/suzent}"
SUZENT_BRANCH="${SUZENT_BRANCH:-main}"
MIN_NODE_MAJOR=20

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
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
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
    curl -LsSf https://astral.sh/uv/install.sh | sh
    refresh_path
fi
command -v uv &>/dev/null || die "uv installation failed. See https://docs.astral.sh/uv/"
ok "uv $(uv --version | awk '{print $2}')"

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

    git fetch origin
    git checkout "$SUZENT_BRANCH" 2>/dev/null || true
    git pull origin "$SUZENT_BRANCH"
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
info "Syncing Python dependencies (uv sync)..."
uv sync || die "uv sync failed — check errors above."
ok "Python dependencies ready"

# ── Install / sync frontend dependencies ─────────────────────────────────────
info "Installing frontend dependencies (npm install)..."
(cd frontend && npm install) || die "npm install failed in frontend/."
ok "Frontend dependencies ready"

# ── Install / sync src-tauri JS dependencies ──────────────────────────────────
info "Installing src-tauri dependencies (npm install)..."
(cd src-tauri && npm install) || die "npm install failed in src-tauri/."
ok "Tauri JS dependencies ready"

# ── Playwright Chromium ───────────────────────────────────────────────────────
if [ "${SUZENT_SKIP_PLAYWRIGHT:-0}" != "1" ]; then
    info "Installing Playwright Chromium (for web browsing tool)..."
    uv run playwright install chromium || warn "Playwright install failed — web browsing may not work (non-fatal)."
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
