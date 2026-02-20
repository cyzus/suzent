#!/bin/bash
set -e

echo "========================================"
echo "   SUZENT Tauri Build Pipeline"
echo "========================================"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Step 1: Build frontend
echo ""
echo "[1/3] Building frontend..."
cd "$PROJECT_ROOT/frontend"
npm install
npm run build

# Step 2: Bundle Python backend
echo ""
echo "[2/3] Bundling Python backend..."
cd "$PROJECT_ROOT"
python scripts/bundle_python.py

# Step 3: Build Tauri application
echo ""
echo "[3/3] Building Tauri application..."
cd "$PROJECT_ROOT/src-tauri"
npm run build

echo ""
echo "Build complete!"
echo "Artifacts: $PROJECT_ROOT/src-tauri/target/release/bundle/"
