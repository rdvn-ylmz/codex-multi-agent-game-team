#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TITLE="${TITLE:-Gameplay Vertical Slice}"
PROFILE="low-spec"
STOP_WHEN_DONE=0
SKIP_AUTH=0
ROLES="concept,game_design,narrative,player_experience,coder,reviewer,qa,security,sre,devops"
BRIEF_FILE="$ROOT_DIR/team/prompts/gameplay_vertical_slice_brief.md"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title)
      TITLE="${2:-$TITLE}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-low-spec}"
      shift 2
      ;;
    --roles)
      ROLES="${2:-$ROLES}"
      shift 2
      ;;
    --brief-file)
      BRIEF_FILE="${2:-$BRIEF_FILE}"
      shift 2
      ;;
    --stop-when-done)
      STOP_WHEN_DONE=1
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

if [[ ! -f "$BRIEF_FILE" ]]; then
  echo "Brief file not found: $BRIEF_FILE" >&2
  exit 1
fi

BRIEF="$(cat "$BRIEF_FILE")"
cmd=(
  "$ROOT_DIR/scripts/run_pipeline.sh"
  --title "$TITLE"
  --brief "$BRIEF"
  --roles "$ROLES"
  --profile "$PROFILE"
)
if [[ "$STOP_WHEN_DONE" -eq 1 ]]; then
  cmd+=(--stop-when-done)
fi
if [[ "$SKIP_AUTH" -eq 1 ]]; then
  cmd+=(--skip-auth-check)
fi

"${cmd[@]}"

