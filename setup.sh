#!/usr/bin/env bash
# Setup script for gh-apple-notes-mcp.
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "==> Setting up gh-apple-notes-mcp..."

command -v python3 >/dev/null 2>&1 || {
    echo "ERROR: python3 not installed" >&2; exit 1;
}

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "    Creating venv..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

echo "    Installing deps..."
# shellcheck disable=SC1091
source "$SCRIPT_DIR/.venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -e "$SCRIPT_DIR[dev]"

echo "    Running tests..."
pytest -q "$SCRIPT_DIR/tests" || { echo "ERROR: tests failed" >&2; exit 1; }

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
echo ""
echo "==> MCP server ready. Add to ~/.claude.json:"
echo ""
echo '  "gh-apple-notes": {'
echo '    "command": "'$PYTHON_BIN'",'
echo '    "args": ["-m", "gh_apple_notes_mcp"]'
echo '  }'
echo ""
echo "If you have an existing 'apple-notes' entry (disco-trooper), replace it."
echo "After editing ~/.claude.json, restart Claude Code."
echo ""
echo "macOS permissions required:"
echo "  1. Full Disk Access for your terminal (System Settings → Privacy & Security)"
echo "  2. Automation permission for Notes (prompted on first write)"
echo ""
echo "==> Setup complete."
