#!/usr/bin/env bash
# One-shot installer for Apex BTC Spot Agent.
# Creates a venv, installs dependencies, and seeds .env from .env.example.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Error: $PYTHON not found. Install Python 3.8+ and retry." >&2
    exit 1
fi

echo ">> Creating virtualenv in $VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"

# shellcheck source=/dev/null
. "$VENV_DIR/bin/activate"

echo ">> Upgrading pip"
pip install --upgrade pip

echo ">> Installing requirements"
pip install -r requirements.txt

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ">> Created .env from .env.example — edit it and paste your API keys."
    else
        echo ">> No .env.example found; skipping .env creation."
    fi
else
    echo ">> .env already exists; leaving it untouched."
fi

chmod +x run.sh 2>/dev/null || true

echo
echo "Install complete. Next steps:"
echo "  1. Edit .env with your Binance API keys."
echo "  2. Start the bot:  ./run.sh"
