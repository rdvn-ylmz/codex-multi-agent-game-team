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
- `/task <role> | <title> | <description>`
- `/run <role> | <title> | <description>`
- `/dispatch [TASK-ID]`
- `/stop`
- `/exit`

## Shutdown / resume

```bash
./scripts/stop_team.sh
./scripts/resume_team.sh --profile low-spec
./scripts/team_status.sh
```

State is persisted under `team/state/` using JSON + JSONL event log for restart recovery.

## GitHub bootstrap

```bash
./scripts/bootstrap_repo.sh codex-multi-agent-game-team public
```

This initializes git (if needed), creates a GitHub repo, sets `origin`, and pushes the current branch.
