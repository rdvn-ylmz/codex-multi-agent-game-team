#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="low-spec"
OPEN_CHAT=1
SKIP_AUTH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-low-spec}"
      shift 2
      ;;
    --no-chat)
      OPEN_CHAT=0
      shift
      ;;
    --skip-auth-check)
      SKIP_AUTH=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$PROFILE" == "low-spec" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/team/config/profile.low-spec.env"
fi

export TEAM_PROFILE="$PROFILE"

cmd=(python3 "$ROOT_DIR/team/orchestrator.py" resume)
if [[ "$SKIP_AUTH" -eq 1 ]]; then
  cmd+=(--skip-auth-check)
fi
"${cmd[@]}"

if [[ "$OPEN_CHAT" -eq 1 ]]; then
  python3 "$ROOT_DIR/team/orchestrator.py" chat
fi
