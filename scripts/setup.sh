#!/usr/bin/env bash
set -euo pipefail

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ".env created from .env.example"
fi

python -m venv .venv || true
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

echo "Setup complete."
echo "Fill .env next."
echo "Then run: docker compose up --build"
