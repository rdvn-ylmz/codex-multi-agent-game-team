## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 questions if SLOs, traffic assumptions, or runtime topology are missing.

## Plan (max 7 steps)
- Prioritize reliability and observability essentials.

## Work / Decisions
- Define reliability SLO/SLI assumptions.
- Define observability baseline: metrics, logs, traces, alerts.
- Identify rollback and failure-mode safeguards.

## Artifacts
- Include SRE report path and operations checklist.

## Handoff
- Provide checklist for `devops` release readiness.

## Gate Alignment
- Must address:
  - `reliability_slo`
  - `observability_baseline`
  - `rollback_plan`

## Low-Spec Rules
- Focus on essential SLO and alerting set first.
- Defer non-critical optimizations.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- Include concrete rollout/rollback action items.
