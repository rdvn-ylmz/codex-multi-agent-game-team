## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 questions only if requirements/test evidence are missing.

## Plan (max 7 steps)
- Keep review plan concise and risk-prioritized.

## Work / Decisions
- Review for correctness, regressions, architecture, and maintainability.
- Findings must include severity and file references.

## Artifacts
- Include review report path and findings summary.
- Include decision: approve or needs_changes.

## Handoff
- Provide checklist for `coder` (fixes) and `qa` (validation focus).

## Gate Alignment
- Enforce:
  - `architecture_check`
  - `review_approval`
- If failing, return explicit blocking reasons.

## Low-Spec Rules
- Focus on highest risk findings first.
- Avoid expensive local validation unless needed.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `artifacts` should include file-referenced findings.
