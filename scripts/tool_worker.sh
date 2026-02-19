#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${1:-}" == "--loop" ]]; then
  shift
  python3 "$ROOT_DIR/team/tools/run_tool.py" run --loop --max-jobs 0 "$@"
else
  python3 "$ROOT_DIR/team/tools/run_tool.py" run --max-jobs "${1:-1}"
fi

