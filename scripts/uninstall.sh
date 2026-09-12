#!/bin/bash

SHIM_PATH="$HOME/.local/bin/suzent"

# Only the launcher entries recorded in .suzent/shortcuts.json are removed, so
# anything the user made by hand survives.
if [ -x ".venv/bin/python" ]; then
    echo -e "\033[0;33mRemoving launcher shortcuts...\033[0m"
    .venv/bin/python -m suzent.cli shortcuts --remove \
        || echo -e "\033[0;36mℹ️ No launcher shortcuts were removed\033[0m"
fi

if [ -f "$SHIM_PATH" ]; then
    echo -e "\033[0;33mRemoving '$SHIM_PATH'...\033[0m"
    rm "$SHIM_PATH"
    echo -e "\033[0;32m✅ Removed 'suzent' command\033[0m"
else
    echo -e "\033[0;36mℹ️ 'suzent' command not found at $SHIM_PATH\033[0m"
fi

echo ""
echo "To completely remove the project, delete this directory:"
echo "  $(pwd)"
