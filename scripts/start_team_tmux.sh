#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="codex-team"
PROFILE="low-spec"
NO_ATTACH=0
SKIP_AUTH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session)
      SESSION_NAME="${2:-codex-team}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-low-spec}"
      shift 2
      ;;
    --no-attach)
      NO_ATTACH=1
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

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not found. Please install tmux first." >&2
  exit 1
fi

start_cmd=("$ROOT_DIR/scripts/start_team.sh" --profile "$PROFILE" --no-chat)
if [[ "$SKIP_AUTH" -eq 1 ]]; then
  start_cmd+=(--skip-auth-check)
fi
"${start_cmd[@]}"

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux kill-session -t "$SESSION_NAME"
fi

tmux new-session -d -s "$SESSION_NAME" -n control "cd '$ROOT_DIR' && python3 team/orchestrator.py chat"
tmux split-window -h -t "$SESSION_NAME:control" "cd '$ROOT_DIR' && watch -n 2 ./scripts/team_status.sh"
tmux split-window -v -t "$SESSION_NAME:control.1" "cd '$ROOT_DIR' && tail -f team/state/events.jsonl"
tmux select-layout -t "$SESSION_NAME:control" tiled

tmux new-window -t "$SESSION_NAME" -n agents "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh concept"
tmux split-window -h -t "$SESSION_NAME:agents" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh coder"
tmux split-window -v -t "$SESSION_NAME:agents.0" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh reviewer"
tmux split-window -v -t "$SESSION_NAME:agents.1" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh qa"
tmux select-layout -t "$SESSION_NAME:agents" tiled

tmux new-window -t "$SESSION_NAME" -n debate "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh council_red"
tmux split-window -h -t "$SESSION_NAME:debate" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh council_blue"
tmux split-window -v -t "$SESSION_NAME:debate.0" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh council_green"
tmux split-window -v -t "$SESSION_NAME:debate.1" "cd '$ROOT_DIR' && ./scripts/watch_role_events.sh orchestrator"
tmux select-layout -t "$SESSION_NAME:debate" tiled

if [[ "$NO_ATTACH" -eq 0 ]]; then
  tmux attach -t "$SESSION_NAME"
else
  echo "tmux session started: $SESSION_NAME"
  echo "Attach with: tmux attach -t $SESSION_NAME"
fi
