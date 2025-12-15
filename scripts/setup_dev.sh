#!/bin/bash
# Development environment setup script for Suzent

set -e

echo "🚀 Setting up Suzent development environment..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
python_version=$(python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.12"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python $required_version or higher is required (found $python_version)"
    exit 1
fi
echo -e "${GREEN}✓ Python $python_version${NC}"

# Check if uv is installed
echo -e "${YELLOW}Checking for uv package manager...${NC}"
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
echo -e "${GREEN}✓ uv installed${NC}"

# Install Python dependencies
echo -e "${YELLOW}Installing Python dependencies...${NC}"
uv sync --extra dev
echo -e "${GREEN}✓ Python dependencies installed${NC}"

# Install Playwright for WebpageTool
echo -e "${YELLOW}Installing Playwright browsers...${NC}"
uv run playwright install chromium
echo -e "${GREEN}✓ Playwright installed${NC}"

# Check Node.js version
echo -e "${YELLOW}Checking Node.js version...${NC}"
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required but not installed"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi
node_version=$(node --version | cut -d'v' -f2 | cut -d. -f1)
if [ "$node_version" -lt 18 ]; then
    echo "❌ Node.js 18+ is required (found v$node_version)"
    exit 1
fi
echo -e "${GREEN}✓ Node.js v$(node --version)${NC}"

# Install frontend dependencies
echo -e "${YELLOW}Installing frontend dependencies...${NC}"
cd frontend
npm install
cd ..
echo -e "${GREEN}✓ Frontend dependencies installed${NC}"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}⚠️  Please edit .env and add your API keys${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Create default config if it doesn't exist
if [ ! -f config/default.yaml ]; then
    echo -e "${YELLOW}Creating default configuration...${NC}"
    cp config/default.example.yaml config/default.yaml
    echo -e "${GREEN}✓ Configuration file created${NC}"
fi

# Run tests to verify setup
echo -e "${YELLOW}Running tests to verify setup...${NC}"
export OPENAI_API_KEY="test-key"
export LOG_LEVEL="ERROR"
if uv run pytest test/ -v; then
    echo -e "${GREEN}✓ Tests passed${NC}"
else
    echo -e "${YELLOW}⚠️  Some tests failed (this is okay for initial setup)${NC}"
fi

echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "To start development:"
echo "  1. Edit .env and add your API keys"
echo "  2. Start backend:  python src/suzent/server.py"
echo "  3. Start frontend: cd frontend && npm run dev"
echo ""
echo "Optional: Set up PostgreSQL for memory system"
echo "  See docs/MEMORY_SYSTEM_DESIGN.md for details"
echo ""
