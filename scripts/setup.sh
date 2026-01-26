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

# 2. Install uv if missing
if ! command -v "uv" &> /dev/null; then
    echo -e "\033[0;33mInstalling uv...\033[0m"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env 2>/dev/null || true
    export PATH="$HOME/.cargo/bin:$PATH"
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

# 6. Install Frontend Dependencies
echo -e "\033[0;33mInstalling frontend dependencies...\033[0m"
cd frontend
npm install
cd ..

echo -e "\033[0;32m✅ Setup Complete!\033[0m"
echo "To start Suzent, run:"
echo -e "\033[0;36m  ./scripts/start-tauri-dev.sh\033[0m"
