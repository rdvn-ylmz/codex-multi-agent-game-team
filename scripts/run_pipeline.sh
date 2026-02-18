#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROFILE="low-spec"
TITLE=""
BRIEF=""
ROLES=""
CONTINUE_ON_FAILURE=0
STOP_WHEN_DONE=0
SKIP_AUTH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="${2:-low-spec}"
      shift 2
      ;;
    --title)
      TITLE="${2:-}"
      shift 2
      ;;
    --brief)
      BRIEF="${2:-}"
      shift 2
      ;;
    --roles)
      ROLES="${2:-}"
      shift 2
      ;;
    --continue-on-failure)
      CONTINUE_ON_FAILURE=1
      shift
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

if [[ -z "$TITLE" || -z "$BRIEF" ]]; then
  echo "Usage: ./scripts/run_pipeline.sh --title \"...\" --brief \"...\" [--roles r1,r2] [--profile low-spec] [--continue-on-failure] [--stop-when-done]" >&2
  exit 1
fi

if [[ "$PROFILE" == "low-spec" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT_DIR/team/config/profile.low-spec.env"
fi
export TEAM_PROFILE="$PROFILE"

start_cmd=(python3 "$ROOT_DIR/team/orchestrator.py" start)
if [[ "$SKIP_AUTH" -eq 1 ]]; then
  start_cmd+=(--skip-auth-check)
fi
"${start_cmd[@]}"

pipeline_cmd=(python3 "$ROOT_DIR/team/orchestrator.py" pipeline "$TITLE" "$BRIEF")
if [[ -n "$ROLES" ]]; then
  pipeline_cmd+=(--roles "$ROLES")
fi

create_output="$("${pipeline_cmd[@]}")"
printf '%s\n' "$create_output"

pipeline_id="$(printf '%s\n' "$create_output" | awk '/^Created PIPE-/{print $2; exit}')"
if [[ -z "$pipeline_id" ]]; then
  echo "Failed to parse pipeline ID from orchestrator output" >&2
  exit 1
fi

run_cmd=(python3 "$ROOT_DIR/team/orchestrator.py" run-pipeline "$pipeline_id")
if [[ "$CONTINUE_ON_FAILURE" -eq 1 ]]; then
  run_cmd+=(--continue-on-failure)
fi
"${run_cmd[@]}"

python3 "$ROOT_DIR/team/orchestrator.py" status

if [[ "$STOP_WHEN_DONE" -eq 1 ]]; then
  python3 "$ROOT_DIR/team/orchestrator.py" stop
fi
