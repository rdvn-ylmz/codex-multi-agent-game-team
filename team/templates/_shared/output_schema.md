# Shared Output Schema (All Stages)

All stages MUST output:

## TASK META
- task_id
- owner

## ACCEPTANCE CRITERIA
- checklist + PASS/FAIL notes

## ARTIFACTS
- Files changed / produced
- Commands run
- Notes

## RISKS / LIMITATIONS
- risks + mitigations

## HANDOFF
- next role action items checklist

## MACHINE-READABLE FOOTER
- JSON block with: task_id, owner, status, acceptance_criteria, artifacts, handoff_to, risks, next_role_action_items
