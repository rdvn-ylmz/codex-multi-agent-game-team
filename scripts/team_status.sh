#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "--json" ]]; then
  python3 "$ROOT_DIR/team/orchestrator.py" status --json
else
  python3 "$ROOT_DIR/team/orchestrator.py" status
fi
