#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLE="${1:-}"
if [[ -z "$ROLE" ]]; then
  echo "Usage: ./scripts/watch_role_events.sh <role>" >&2
  exit 1
fi

EVENT_FILE="${TEAM_EVENTS_PATH:-$ROOT_DIR/team/state/events.jsonl}"
mkdir -p "$(dirname "$EVENT_FILE")"
touch "$EVENT_FILE"

tail -n 200 -F "$EVENT_FILE" | python3 -u "$ROOT_DIR/scripts/watch_role_events.py" "$ROLE"
