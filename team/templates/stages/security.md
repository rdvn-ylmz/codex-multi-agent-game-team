## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 questions if trust boundaries, auth, or data flows are unclear.

## Plan (max 7 steps)
- Prioritize critical attack paths first.

## Work / Decisions
- Provide threat-model delta (STRIDE-style where applicable).
- For each issue include severity, exploit scenario, and fix recommendation.

## Artifacts
- Include security report path and prioritized findings list.
- Include explicit unresolved high/critical risks.

## Handoff
- Provide checklist for `sre` and `devops`.
- Call out controls needed before release.

## Gate Alignment
- Align to `security_scan` and release hardening requirements.

## Low-Spec Rules
- Focus on highest-impact threat paths.
- Keep scans/checks lightweight locally; full scans CI.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `risks` must include outstanding critical/high items if any.
