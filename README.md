# Codex Multi-Session Team (Low-Spec, Codex-Only)

This repository bootstraps a Codex-only multi-agent workflow that runs in a single terminal chat while coordinating role-based sessions.

## What is included

- `team/orchestrator.py`: queue/state orchestrator
- `scripts/start_team.sh`: start system and open terminal chat
- `scripts/stop_team.sh`: graceful stop
- `scripts/resume_team.sh`: resume after shutdown
- `scripts/team_status.sh`: runtime status
- `team/config/*.yaml`: roles/workflow/gates/policy configs

## Quick start

```bash
./scripts/start_team.sh --profile low-spec
```

Then use chat commands:

- `/help`
- `/status`
- `/agents`
- `/queue`
- `/pipelines`
- `/task <role> | <title> | <description>`
- `/run <role> | <title> | <description>`
- `/pipeline <title> | <brief>`
- `/run-pipeline <title> | <brief>`
- `/dispatch [TASK-ID]`
- `/drain [max_tasks]`
- `/stop`
- `/exit`

## Shutdown / resume

```bash
./scripts/stop_team.sh
./scripts/resume_team.sh --profile low-spec
./scripts/team_status.sh
```

State is persisted under `team/state/` using JSON + JSONL event log for restart recovery.

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

## GitHub bootstrap

```bash
./scripts/bootstrap_repo.sh codex-multi-agent-game-team public
```

This initializes git (if needed), creates a GitHub repo, sets `origin`, and pushes the current branch.
