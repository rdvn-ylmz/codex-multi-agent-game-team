## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 questions if controls, platform limits, or accessibility targets are unclear.

## Plan (max 7 steps)
- Prioritize first-session usability and friction reduction.

## Work / Decisions
- Define FTUE, UX flow, and retention-critical interaction points.
- Explain why each UX decision helps completion and retention.

## Artifacts
- MUST include:
  - `docs/ux_flow.md`
- Include FTUE steps with expected user actions/results.

## Handoff
- Provide concrete checklist for `coder`.
- Include top UX risks for `reviewer` and `qa`.

## Gate Alignment
- Ensure UX flow can be smoke-tested by QA.

## Low-Spec Rules
- Keep flows practical and implementation-ready.
- Avoid heavy prototype/tooling requirements.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `artifacts` must include `docs/ux_flow.md`.
