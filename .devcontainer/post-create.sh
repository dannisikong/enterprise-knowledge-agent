#!/usr/bin/env bash
set -euo pipefail

echo "Installing backend runtime and development dependencies..."
python -m pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-dev.txt

echo "Installing frontend dependencies..."
cd frontend
npm install --no-audit --no-fund

echo "Codespaces environment setup complete."
