#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROFILE="low-spec"
PROJECT_NAME=""
TITLE=""
BRIEF=""
ROLES=""
PROJECTS_DIR="$ROOT_DIR/projects"
CONTINUE_ON_FAILURE=0
STOP_WHEN_DONE=0
SKIP_AUTH=0

usage() {
  cat <<EOF
Usage:
  ./scripts/run_fresh_project.sh \\
    --name "my-game" \\
    --brief "One paragraph project brief" \\
    [--title "Pipeline title"] \\
    [--roles concept,game_design,coder] \\
    [--projects-dir /path/to/projects] \\
    [--profile low-spec] \\
    [--continue-on-failure] \\
    [--stop-when-done] \\
    [--skip-auth-check]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      PROJECT_NAME="${2:-}"
      shift 2
      ;;
    --brief)
      BRIEF="${2:-}"
      shift 2
      ;;
    --title)
      TITLE="${2:-}"
      shift 2
      ;;
    --roles)
      ROLES="${2:-}"
      shift 2
      ;;
    --projects-dir)
      PROJECTS_DIR="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-low-spec}"
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
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PROJECT_NAME" || -z "$BRIEF" ]]; then
  usage >&2
  exit 1
fi

if [[ -z "$TITLE" ]]; then
  TITLE="$PROJECT_NAME"
fi

slug="$(printf '%s' "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
if [[ -z "$slug" ]]; then
  slug="project"
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$PROJECTS_DIR"
PROJECTS_DIR_ABS="$(cd "$PROJECTS_DIR" && pwd)"
PROJECT_DIR="$PROJECTS_DIR_ABS/${slug}-${timestamp}"

mkdir -p "$PROJECT_DIR" "$PROJECT_DIR/.team_state" "$PROJECT_DIR/docs" "$PROJECT_DIR/src" "$PROJECT_DIR/assets/text"

cat > "$PROJECT_DIR/README.md" <<EOF
# $PROJECT_NAME

Generated at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Managed by: $ROOT_DIR/scripts/run_fresh_project.sh
EOF

ENV_FILE="$PROJECT_DIR/.team_env"
cat > "$ENV_FILE" <<EOF
export TEAM_PROJECT_ROOT="$PROJECT_DIR"
export TEAM_STATE_PATH="$PROJECT_DIR/.team_state/runtime_state.json"
export TEAM_EVENTS_PATH="$PROJECT_DIR/.team_state/events.jsonl"
export TEAM_PROFILE="$PROFILE"
EOF

# shellcheck source=/dev/null
source "$ENV_FILE"

echo "Project directory created: $PROJECT_DIR"
echo "State file: $TEAM_STATE_PATH"
echo "Events file: $TEAM_EVENTS_PATH"

cmd=("$ROOT_DIR/scripts/run_pipeline.sh" --profile "$PROFILE" --title "$TITLE" --brief "$BRIEF")
if [[ -n "$ROLES" ]]; then
  cmd+=(--roles "$ROLES")
fi
if [[ "$CONTINUE_ON_FAILURE" -eq 1 ]]; then
  cmd+=(--continue-on-failure)
fi
if [[ "$STOP_WHEN_DONE" -eq 1 ]]; then
  cmd+=(--stop-when-done)
fi
if [[ "$SKIP_AUTH" -eq 1 ]]; then
  cmd+=(--skip-auth-check)
fi

"${cmd[@]}"

echo
echo "Project root: $PROJECT_DIR"
echo "To resume later:"
echo "  source \"$ENV_FILE\" && \"$ROOT_DIR/scripts/resume_team.sh\""
echo "To stop:"
echo "  source \"$ENV_FILE\" && \"$ROOT_DIR/scripts/stop_team.sh\""
