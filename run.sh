#!/usr/bin/env bash
# Loads .env, then runs the agent.
set -e
cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a; . ./.env; set +a
else
    echo "No .env file found — copy .env.example to .env and fill it in."
    exit 1
fi

exec python3 apex_btc_agent.py
