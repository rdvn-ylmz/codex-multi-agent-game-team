#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-branch)
      BASE_BRANCH="${2:-main}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repository: $ROOT_DIR" >&2
  exit 1
fi

python3 - "$ROOT_DIR" "$BASE_BRANCH" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
base_branch = sys.argv[2]
config_file = root / "team" / "config" / "workspaces.json"

if not config_file.exists():
    raise SystemExit(f"Workspace config not found: {config_file}")

config = json.loads(config_file.read_text(encoding="utf-8"))
roles = config.get("roles", {})
if not isinstance(roles, dict) or not roles:
    raise SystemExit("No role workspace definitions found in workspaces.json")

for role, rel_path in roles.items():
    workdir = (root / str(rel_path)).resolve()
    branch = f"agent/{role}"

    if workdir.exists():
        print(f"skip {role}: {workdir} (already exists)")
        continue

    workdir.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "worktree", "add", "-B", branch, str(workdir), base_branch]
    print("create", role, "->", workdir)
    subprocess.run(cmd, cwd=root, check=True)

print("workspace setup complete")
PY
