#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: ./scripts/run-agent.sh <module_path> <port>"
  exit 1
fi

MODULE_PATH="$1"
PORT="$2"

source .venv/bin/activate
PYTHONPATH=. uvicorn "${MODULE_PATH}:app" --host 0.0.0.0 --port "${PORT}"
