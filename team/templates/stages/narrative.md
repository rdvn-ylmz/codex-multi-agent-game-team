## Task Meta
- Required fields in final JSON: `task_id`, `owner`, `acceptance_criteria`, `artifacts`.

## Context I Need
- Ask 3-7 concrete questions if tone/world/age-rating constraints are missing.

## Plan (max 7 steps)
- Keep plan short; prioritize story pieces that unblock implementation.

## Work / Decisions
- Define narrative arc, mission beats, and key player-facing text assets.
- Keep language aligned with gameplay pacing and onboarding.

## Artifacts
- MUST include:
  - `docs/narrative.md`
  - At least one file under `assets/text/`
- Include copy snippets usable by UI/gameplay implementation.

## Handoff
- Provide checklist for `player_experience` and `coder`.
- Mark text assets that are MVP-critical.

## Gate Alignment
- Ensure narrative assets are versionable and testable (no vague placeholders).

## Low-Spec Rules
- Prefer concise, reusable text blocks.
- Avoid overproducing long lore not needed for MVP.

## Output Contract
- End response with one `json` fenced block following orchestrator contract.
- `artifacts` must include `docs/narrative.md` and `assets/text/*` paths.
