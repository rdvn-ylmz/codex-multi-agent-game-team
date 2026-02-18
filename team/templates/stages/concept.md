## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.
- Target status: `done` or `needs_changes`.

## Context I Need
- If context is missing, ask 3-7 concrete questions before finalizing.
- Keep questions scoped to player segment, problem, constraints, and success metric.

## Plan (max 7 steps)
- Use a short plan with no more than 7 steps.
- Prefer smallest high-leverage work first (low-spec rule).

## Work / Decisions
- Produce 2-3 concept options, then recommend one.
- Explain tradeoffs: build risk, novelty, retention potential, delivery speed.
- Keep analysis concise and implementation-oriented.

## Artifacts
- MUST include at least:
  - `docs/concept.md`
- Include brief market assumptions and validation approach.

## Handoff
- Provide checklist for `game_design`.
- Include top assumptions to validate early.

## Gate Alignment
- Ensure proposed concept can be validated with MVP scope.
- Avoid ideas that force high infra complexity before proof.

## Low-Spec Rules
- Minimize file edits and command count.
- Heavy research/experiments should be deferred to CI/next stage.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `next_role_action_items` must contain concrete checklist items for `game_design`.
