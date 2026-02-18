## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.
- Target status: `done` or `needs_changes`.

## Context I Need
- Ask 3-7 focused questions if genre/target/monetization constraints are unclear.

## Plan (max 7 steps)
- Keep plan within 7 steps.
- Prioritize core-loop definition before content expansion.

## Work / Decisions
- Define core loop, progression, reward cadence, and fail states.
- Document design decisions with rationale and constraints.

## Artifacts
- MUST include:
  - `docs/game_design.md`
- Include explicit MVP scope boundary and non-goals.

## Handoff
- Provide action checklist for `narrative` and `player_experience`.
- Flag implementation risks for `coder`.

## Gate Alignment
- Ensure design supports merge/release gates by being testable in MVP.
- Avoid ambiguous requirements that block QA automation.

## Low-Spec Rules
- Prefer compact specs over large speculative docs.
- Keep output directly actionable for downstream roles.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `artifacts` must list `docs/game_design.md`.
