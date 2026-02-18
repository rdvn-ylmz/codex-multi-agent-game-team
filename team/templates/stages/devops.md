## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 questions if deployment targets, secrets, or rollback constraints are unclear.

## Plan (max 7 steps)
- Keep release plan concise and executable.

## Work / Decisions
- Provide deployment sequence and verification points.
- Provide rollback steps and incident trigger criteria.

## Artifacts
- Include release checklist and rollback procedure docs.

## Handoff
- Provide final go/no-go checklist for orchestrator/user.

## Gate Alignment
- Must address release gates:
  - `performance_budget`
  - `reliability_slo`
  - `observability_baseline`
  - `rollback_plan`

## Low-Spec Rules
- Prefer simple deployment steps with clear safety checks.
- Avoid heavyweight local infra simulation.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `status` should clearly indicate release readiness.
