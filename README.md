# Codex Multi-Session Team (Low-Spec, Codex-First + Free Fallback)

This repository bootstraps a multi-agent workflow that runs in a single terminal chat while coordinating role-based sessions. It uses Codex first, then can fall back to free OpenCode models when Codex (or another model) hits limits.

## What is included

- `team/orchestrator.py`: queue/state orchestrator
- `scripts/start_team.sh`: start system and open terminal chat
- `scripts/stop_team.sh`: graceful stop
- `scripts/resume_team.sh`: resume after shutdown
- `scripts/team_status.sh`: runtime status
- `scripts/run_pipeline.sh`: one-command pipeline create + execute
- `scripts/run_gameplay_vertical_slice.sh`: one-command pipeline using a stronger playable-game brief
- `scripts/run_fresh_project.sh`: create isolated project folder + run from scratch
- `scripts/start_team_tmux.sh`: start tmux multi-pane cockpit
- `scripts/stop_team_tmux.sh`: stop tmux cockpit + team
- `scripts/setup_workspaces.sh`: create per-role git workspaces (worktree)
- `scripts/workspaces_status.sh`: inspect role workspaces
- `team/tools/run_tool.py`: tool adapter queue for music/image asset jobs
- `scripts/tool_worker.sh`: run tool queue worker
- `scripts/tool_status.sh`: inspect tool queue + summary
- `scripts/live_monitor.sh`: web monitor (`/api/snapshot`) for tasks/events/tool-jobs/assets
- `.github/workflows/quality-gates.yml`: CI quality gates
- `scripts/lint.sh`, `scripts/test.sh`, `scripts/security_scan.sh`, `scripts/perf_budget.sh`
- `team/config/*.yaml`, `team/config/workspaces.json`: runtime configs
- `team/config/model_router.json`: per-role model/backend fallback chain
- `team/config/quota_policy.json`: quota detection markers and defer policy
- `team/config/tools.json`: external/builtin asset tool registry
- `team/config/output_contract.schema.json`: machine-readable output schema
- `team/templates/stages/*.md`: role-specific stage templates
- `team/prompts/orchestrator_system.md`, `team/prompts/council_*.md`: orchestration and debate personas

## Quick start

```bash
./scripts/start_team.sh --profile low-spec
```

The chat now auto-dispatches normal text messages and prints the report directly, so you can ask questions and receive responses in the same pane.

Then use chat commands:

- `/help`
- `/status`
- `/agents`
- `/queue`
- `/pipelines`
- `/debates`
- `/task <role> | <title> | <description>`
- `/run <role> | <title> | <description>`
- `/pipeline <title> | <brief>`
- `/run-pipeline <title> | <brief>`
- `/debate <title> | <topic>`
- `/run-debate <title> | <topic>`
- `/dispatch [TASK-ID]`
- `/drain [max_tasks]`
- `/stop`
- `/exit`

## tmux cockpit (visible sessions)

This gives you an on-screen multi-window environment:

1. `control`: interactive chat + status + global events
2. `agents`: role event streams (concept/coder/reviewer/qa)
3. `debate`: council agent streams (red/blue/green + orchestrator)
4. `tools`: tool queue status + asset manifest + filtered events

Start:

```bash
./scripts/start_team_tmux.sh --profile low-spec
```

Stop:

```bash
./scripts/stop_team_tmux.sh
```

## Shutdown / resume

```bash
./scripts/stop_team.sh
./scripts/resume_team.sh --profile low-spec
./scripts/team_status.sh
```

State is persisted under `team/state/` using JSON + JSONL event log for restart recovery.

## Debate workflow (3-agent discussion)

Create debate:

```bash
python3 team/orchestrator.py debate "Stack decision" "Do we keep modular monolith or split services?"
python3 team/orchestrator.py debates
python3 team/orchestrator.py run-debate DEBATE-0001
```

Roles:

- `council_red`: engineering architecture position
- `council_blue`: reliability/risk/security position
- `council_green`: product/growth/time-to-market position
- `orchestrator`: moderator synthesis

## Pipeline workflow

Create a role chain pipeline from CLI:

```bash
python3 team/orchestrator.py pipeline "Browser Game MVP" "Build an initial playable loop and release checklist."
python3 team/orchestrator.py pipelines
python3 team/orchestrator.py run-pipeline PIPE-0001
```

Drain queue automatically:

```bash
python3 team/orchestrator.py drain --max-tasks 5
```

One-command pipeline create + run:

```bash
./scripts/run_pipeline.sh \
  --title "Browser Game MVP" \
  --brief "Build a playable loop, verify quality gates, and prepare release plan." \
  --profile low-spec
```

Optional flags:

- `--roles concept,game_design,coder,reviewer,qa,security,sre,devops`
- `--continue-on-failure`
- `--stop-when-done`
- `--skip-auth-check`

Run with the included stronger playable-game brief:

```bash
./scripts/run_gameplay_vertical_slice.sh --profile low-spec
```

Run in a brand-new isolated project directory (recommended for fresh starts):

```bash
./scripts/run_fresh_project.sh \
  --name "browser-game-mvp" \
  --brief "Build a playable browser game loop and ship-ready checklist." \
  --profile low-spec
```

This creates a new folder under `projects/`, stores state/events inside that folder, and runs the full pipeline there.

## Role workspaces and git/github

Role-specific workspaces are configured in `team/config/workspaces.json`.
If a workspace exists, the orchestrator runs that role's Codex task in that workspace directory.

Create workspaces (git worktrees):

```bash
./scripts/setup_workspaces.sh --base-branch main
./scripts/workspaces_status.sh
```

This allows agents to operate on role branches like `agent/coder`, `agent/reviewer`, etc.

## Stage templates

Pipeline stages inject role templates from `team/templates/stages/<role>.md` into each task description.
Use these templates to standardize acceptance criteria and handoff quality for concept/design/story/engineering/release work.
Templates now enforce a fixed skeleton:

1. `Task Meta`
2. `Context I Need`
3. `Plan (max 7 steps)`
4. `Work / Decisions`
5. `Artifacts`
6. `Handoff`

Each task must end with a machine-readable JSON footer contract.

## Output contract

Schema: `team/config/output_contract.schema.json`

Required JSON fields:

- `task_id`
- `owner`
- `status`
- `acceptance_criteria`
- `artifacts`
- `risks`
- `handoff_to`
- `next_role_action_items`

If JSON contract is invalid, orchestrator retries once (`MAX_OUTPUT_FORMAT_RETRIES=1`) and fails the task if still invalid.

## Model routing and quota defer

- Model chain config: `team/config/model_router.json`
- Quota policy config: `team/config/quota_policy.json`
- Dispatch behavior:
  1. Try configured models in order for the role.
  2. If one model fails with quota/rate-limit, automatically try the next model.
  3. If all models are quota-exhausted, task is deferred (`retry_at`) instead of failed.
- Queue/Status behavior:
  - deferred tasks are skipped by normal dispatch/drain until `retry_at`.
  - `status` output shows `deferred=<count>`.

## Tool adapter (music/image queue)

Submit jobs:

```bash
python3 team/tools/run_tool.py submit \
  --tool music_tone \
  --prompt "90bpm boss intro loop" \
  --task-id TASK-1234 \
  --role narrative \
  --param duration_sec=8 \
  --param frequency_hz=280

python3 team/tools/run_tool.py submit \
  --tool image_svg \
  --prompt "Neon asteroid field key art" \
  --param width=1280 \
  --param height=720
```

Run worker:

```bash
./scripts/tool_worker.sh 2           # run up to 2 jobs and exit
./scripts/tool_worker.sh --loop      # keep processing queue
```

Inspect queue and assets:

```bash
./scripts/tool_status.sh
python3 team/tools/run_tool.py manifest --limit 20
```

Generated files:

- jobs state: `${TEAM_STATE_PATH%/*}/tool_jobs.json`
- assets: `${TEAM_PROJECT_ROOT}/assets/...`
- manifest: `${TEAM_PROJECT_ROOT}/assets/manifest.json`

## Live monitor

Start:

```bash
./scripts/live_monitor.sh --host 127.0.0.1 --port 8787
```

Open:

- `http://127.0.0.1:8787`
- JSON snapshot: `http://127.0.0.1:8787/api/snapshot`

## Quality gates

CI workflow runs on push and PR:

1. Lint (`./scripts/lint.sh`)
2. Tests (`./scripts/test.sh`)
3. Security scan (`./scripts/security_scan.sh`)
4. Performance budget (`./scripts/perf_budget.sh`)

Local run:

```bash
./scripts/lint.sh
./scripts/test.sh
./scripts/security_scan.sh
./scripts/perf_budget.sh
```

## GitHub bootstrap

```bash
./scripts/bootstrap_repo.sh codex-multi-agent-game-team public
```

This initializes git (if needed), creates a GitHub repo, sets `origin`, and pushes the current branch.
