#!/usr/bin/env bash
set -euo pipefail

if ! python3 -m bandit --version >/dev/null 2>&1; then
  echo "bandit is not installed. Install dev tools with: python -m pip install -r requirements-dev.txt" >&2
  exit 2
fi

if ! python3 -m pip_audit --version >/dev/null 2>&1; then
  echo "pip-audit is not installed. Install dev tools with: python -m pip install -r requirements-dev.txt" >&2
  exit 2
fi

python3 -m bandit -q -r team scripts -x tests -s B404,B603,B607
python3 -m pip_audit -r requirements.txt
