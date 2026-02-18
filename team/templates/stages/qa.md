## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 clarifying questions if expected behavior or environments are unclear.

## Plan (max 7 steps)
- Prioritize smoke flows before regression depth.

## Work / Decisions
- Execute smoke/regression tests and record outcomes.
- Capture reproducible steps for each defect.

## Artifacts
- Include QA report path and tested flow list.
- Include pass/fail per critical flow.

## Handoff
- Provide checklist for `security` and `sre`.
- Highlight unstable areas for release risk.

## Gate Alignment
- Align with merge/release readiness via explicit smoke coverage.

## Low-Spec Rules
- Run fast local tests first.
- Heavy suites should be marked CI-only.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `next_role_action_items` must include concrete test follow-ups.
