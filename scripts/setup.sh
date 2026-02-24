#!/bin/bash
set -e

echo -e "\033[0;36m🤖 Waking up SUZENT...\033[0m"

# 1. Check Prerequisites
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "\033[0;31m$2 is not installed. Please install it and try again.\033[0m"
        exit 1
    fi
}

check_command "git" "Git"
check_command "node" "Node.js"
check_command "curl" "curl"

# 1.1. Check Node.js version (20+ required)
NODE_VERSION=$(node --version | sed 's/^v//')
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo -e "\033[0;31mNode.js version $NODE_VERSION detected. Version 20+ is required.\033[0m"
    echo -e "\033[0;36mPlease upgrade Node.js from https://nodejs.org/\033[0m"
    exit 1
fi
echo -e "\033[0;32m✅ Node.js v$NODE_VERSION\033[0m"

# 1.2. Platform-specific system dependencies
OS_TYPE="$(uname -s)"
case "$OS_TYPE" in
    Darwin)
        # macOS: check for Xcode Command Line Tools
        if ! xcode-select -p &>/dev/null; then
            echo -e "\033[0;33m⚠️  Xcode Command Line Tools not found. Installing...\033[0m"
            xcode-select --install 2>/dev/null || true
            echo -e "\033[0;33m   Please complete the Xcode Tools installation dialog, then re-run this script.\033[0m"
            exit 1
        fi
        echo -e "\033[0;32m✅ Xcode Command Line Tools found.\033[0m"
        ;;
    Linux)
        # Linux: check for Tauri system libraries (GTK, WebKitGTK, etc.)
        MISSING_LIBS=""
        for pkg in libgtk-3-dev libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf; do
            if ! dpkg -s "$pkg" &>/dev/null 2>&1; then
                MISSING_LIBS="$MISSING_LIBS $pkg"
            fi
        done
        if [ -n "$MISSING_LIBS" ]; then
            echo -e "\033[0;33m⚠️  Missing Tauri system dependencies:$MISSING_LIBS\033[0m"
            if command -v apt-get &>/dev/null; then
                echo -e "\033[0;36m   Installing via apt-get (may require sudo password)...\033[0m"
                sudo apt-get update && sudo apt-get install -y $MISSING_LIBS
                if [ $? -ne 0 ]; then
                    echo -e "\033[0;31m   Failed to install system libraries. Please install manually:\033[0m"
                    echo "   sudo apt-get install -y$MISSING_LIBS"
                    exit 1
                fi
            else
                echo -e "\033[0;31m   apt-get not found. Please install these packages with your package manager:\033[0m"
                echo "  $MISSING_LIBS"
                exit 1
            fi
        fi
        echo -e "\033[0;32m✅ Tauri system dependencies satisfied.\033[0m"
        ;;
esac

# Helper for robust shell config updates
update_shell_config() {
    local NEW_PATH="$1"
    local SHELL_NAME=$(basename "$SHELL")
    local CONFIG_FILE=""
    
    if [ "$SHELL_NAME" = "zsh" ]; then
        CONFIG_FILE="$HOME/.zshrc"
    elif [ "$SHELL_NAME" = "bash" ]; then
        if [ -f "$HOME/.bash_profile" ]; then
            CONFIG_FILE="$HOME/.bash_profile"
        else
            CONFIG_FILE="$HOME/.bashrc"
        fi
    else
        # Fallback for other shells
        CONFIG_FILE="$HOME/.profile"
    fi

    # Check if currently in PATH
    if [[ ":$PATH:" == *":$NEW_PATH:"* ]]; then
        return
    fi
    
    # Check if already in config file (simple grep)
    if [ -f "$CONFIG_FILE" ] && grep -q "$NEW_PATH" "$CONFIG_FILE"; then
         return
    fi

    if [ -n "$CONFIG_FILE" ]; then
        echo -e "Do you want to add $NEW_PATH to your PATH in $CONFIG_FILE? (y/n)"
        
        # Capture user input, handling piped execution
        local choice
        if [ -t 0 ]; then
             read -r choice
        else
             if [ -c /dev/tty ]; then
                 read -r choice < /dev/tty
             else
                 echo -e "\033[0;33mUnable to read from TTY. Skipping auto-config.\033[0m"
                 choice="n"
             fi
        fi

        if [[ "$choice" =~ ^[Yy]$ ]]; then
             if echo "" >> "$CONFIG_FILE" 2>/dev/null && echo "export PATH=\"$NEW_PATH:\$PATH\"" >> "$CONFIG_FILE" 2>/dev/null; then
                 echo -e "\033[0;32mAdded to $CONFIG_FILE\033[0m"
                 echo "Please run: source $CONFIG_FILE"
             else
                 echo -e "\033[0;31mError: Could not write to $CONFIG_FILE (Permission denied)\033[0m"
                 echo "Please add the following to your shell config manually:"
                 echo "  export PATH=\"$NEW_PATH:\$PATH\""
             fi
        else
             echo "Please add the following to your shell config manually:"
             echo "  export PATH=\"$NEW_PATH:\$PATH\""
        fi
    else
         echo "Could not detect shell setup. Please add this to your shell config:"
         echo "  export PATH=\"$NEW_PATH:\$PATH\""
    fi
}

# 2. Install uv if missing
if ! command -v "uv" &> /dev/null; then
    echo -e "\033[0;33mInstalling uv...\033[0m"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env 2>/dev/null || true
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 2.5. Install Rust (Required for Tauri)
if ! command -v "cargo" &> /dev/null; then
    echo -e "\033[0;33mRust is missing. Installing Rust (rustup)...\033[0m"
    # Use --no-modify-path to prevent permission errors on restricted systems
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    source "$HOME/.cargo/env"
fi

# 3. Clone Repo (if needed)
REPO_URL="https://github.com/cyzus/suzent.git"
DIR_NAME="suzent"

if [ ! -d ".git" ]; then
    if [ ! -d "$DIR_NAME" ]; then
        echo -e "\033[0;33mCloning Suzent...\033[0m"
        git clone "$REPO_URL"
    fi
    cd "$DIR_NAME"
fi

# 4. Setup .env
if [ ! -f ".env" ]; then
    echo -e "\033[0;33mCreating .env from template...\033[0m"
    cp .env.example .env
    echo -e "\033[0;31mIMPORTANT: Please edit .env with your API keys!\033[0m"
fi

# 5. Install Backend Dependencies
echo -e "\033[0;33mInstalling backend dependencies...\033[0m"
uv sync
if [ $? -ne 0 ]; then
    echo -e "\033[0;31mBackend dependency installation failed (uv sync). Please check errors above.\033[0m"
    exit 1
fi

# 5.5. Install Playwright Chromium browser (needed by browsing tool)
echo -e "\033[0;33mInstalling Playwright Chromium browser...\033[0m"
uv run playwright install chromium || echo -e "\033[0;33m⚠️  Playwright browser install failed (non-fatal, will retry on first use).\033[0m"

# 6. Install Frontend Dependencies
echo -e "\033[0;33mInstalling frontend dependencies...\033[0m"
cd frontend
npm install
if [ $? -ne 0 ]; then
    echo -e "\033[0;31mFrontend dependency installation failed (npm install). Please check errors above.\033[0m"
    cd ..
    exit 1
fi
cd ..

# 7. Install Src-Tauri Dependencies (for CLI)
echo -e "\033[0;33mInstalling src-tauri dependencies...\033[0m"
cd src-tauri
# Remove existing lockfile/modules to ensure platform-specific binaries are fetched
rm -rf node_modules package-lock.json
npm install
if [ $? -ne 0 ]; then
    echo -e "\033[0;31mSrc-tauri dependency installation failed (npm install). Please check errors above.\033[0m"
    cd ..
    exit 1
fi
cd ..

# 7.5. Ensure Tauri resource placeholders exist
# These files are tracked in git but may be missing if:
#   - User cloned before the files were committed (stale .gitignore)
#   - bundle_python.py wiped the resources/ directory
#   - .gitignore negation patterns weren't applied on pull
echo -e "\033[0;33mEnsuring Tauri resource files exist...\033[0m"
git checkout HEAD -- src-tauri/resources/suzent.cmd src-tauri/resources/suzent 2>/dev/null
if [ $? -ne 0 ]; then
    # Files not in git (e.g. older branch) — create placeholders
    RESOURCE_DIR="src-tauri/resources"
    mkdir -p "$RESOURCE_DIR"
    if [ ! -f "$RESOURCE_DIR/suzent.cmd" ]; then
        printf '@echo off\r\nREM Placeholder — actual shim is generated at runtime.\r\n' > "$RESOURCE_DIR/suzent.cmd"
    fi
    if [ ! -f "$RESOURCE_DIR/suzent" ]; then
        printf '#!/bin/sh\n# Placeholder — actual shim is generated at runtime.\n' > "$RESOURCE_DIR/suzent"
        chmod +x "$RESOURCE_DIR/suzent"
    fi
fi

# 8. Setup Global CLI
echo -e "\033[0;33mSetting up 'suzent' command...\033[0m"
INSTALL_DIR="$HOME/.local/bin"
REPO_DIR="$(pwd)"
mkdir -p "$INSTALL_DIR"

# Create shim script
cat > "$INSTALL_DIR/suzent" <<EOF
#!/bin/bash
# Ensure Rust is in PATH
source "\$HOME/.cargo/env" 2>/dev/null || true
REPO_DIR="$REPO_DIR"
if [ ! -d "\$REPO_DIR" ]; then
    echo "Error: Suzent directory not found at \$REPO_DIR"
    echo "Please re-run the setup script or update this shim."
    exit 1
fi
cd "\$REPO_DIR"
uv run suzent "\$@"
EOF

chmod +x "$INSTALL_DIR/suzent"

# Check PATHs
update_shell_config "$HOME/.cargo/bin"
update_shell_config "$INSTALL_DIR"

echo -e "\033[0;32m✅ Setup Complete!\033[0m"
echo "To start Suzent, run:"
echo -e "\033[0;36m  suzent\033[0m"
