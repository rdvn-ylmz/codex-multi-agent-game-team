#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_NAME="${1:-codex-multi-agent-game-team}"
VISIBILITY="${2:-public}"

cd "$ROOT_DIR"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init
fi

if ! git config user.name >/dev/null; then
  git config user.name "rdvn-ylmz"
fi

if ! git config user.email >/dev/null; then
  git config user.email "rdvn-ylmz@users.noreply.github.com"
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  gh repo create "$REPO_NAME" "--$VISIBILITY" --source . --remote origin --push
else
  git push -u origin HEAD
fi
