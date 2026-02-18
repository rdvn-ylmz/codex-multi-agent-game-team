## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 focused questions if implementation scope is ambiguous.

## Plan (max 7 steps)
- Use a short implementation plan.
- Prefer smallest safe change-set first.

## Work / Decisions
- Implement required behavior with maintainable design.
- Document key technical decisions and tradeoffs.
- Note design/resiliency patterns used.

## Artifacts
- Include changed file paths and executed commands.
- Include test evidence and docs updates when relevant.

## Handoff
- Provide checklist for `reviewer` and `qa`.
- Call out exact files/risk areas to inspect.

## Gate Alignment
- Before done, run low-cost checks aligned to:
  - `lint`
  - `unit_tests`
- On low-spec systems, run fast subset locally and state that full checks run in CI.

## Low-Spec Rules
- Minimize touched files and command count.
- Avoid heavy local builds unless absolutely required.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- Include `artifacts` entries for `files_changed` and `commands`.
- `handoff_to` should include `reviewer` and `qa` when code changed.
