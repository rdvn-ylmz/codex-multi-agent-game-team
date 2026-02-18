#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== git worktree list =="
git worktree list

echo
echo "== configured role workspaces =="
python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

root = Path.cwd()
config_file = root / "team" / "config" / "workspaces.json"
if not config_file.exists():
    raise SystemExit("workspaces config not found")

config = json.loads(config_file.read_text(encoding="utf-8"))
roles = config.get("roles", {})
for role, rel in sorted(roles.items()):
    p = (root / str(rel)).resolve()
    status = "exists" if p.exists() else "missing"
    print(f"- {role}: {p} [{status}]")
PY
