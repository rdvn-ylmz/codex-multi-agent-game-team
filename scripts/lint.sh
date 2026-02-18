#!/usr/bin/env bash
set -euo pipefail

if ! python3 -m ruff --version >/dev/null 2>&1; then
  echo "ruff is not installed. Install dev tools with: python -m pip install -r requirements-dev.txt" >&2
  exit 2
fi

python3 -m ruff check .
