# Definition of Done (DoD)

This file defines what "DONE" means across the multi-agent workflow.
All roles must align to these checks.

---

## UNIVERSAL DONE CHECKS (ALL TASKS)

A task is NOT done unless:

- [ ] task_id exists
- [ ] owner is specified
- [ ] acceptance criteria checklist exists
- [ ] artifacts are produced (files, commands, docs, notes)
- [ ] clear handoff or completion state exists
- [ ] machine-readable JSON footer is present

---

## CODER DONE

- [ ] Implementation satisfies acceptance criteria.
- [ ] Minimal necessary files changed.
- [ ] Fast local validation run (or justified skip).
- [ ] Risks documented.
- [ ] Reviewer handoff includes focus areas.

---

## REVIEWER DONE

- [ ] Acceptance criteria explicitly validated.
- [ ] Architecture concerns documented.
- [ ] Findings categorized by severity.
- [ ] Clear APPROVED or CHANGES_REQUESTED decision.

---

## QA DONE

- [ ] Smoke flow tested.
- [ ] Regression risk checked.
- [ ] Edge/negative scenarios included.
- [ ] Evidence recorded.

---

## SECURITY DONE

- [ ] Threat delta reviewed.
- [ ] Input/auth/secrets considered.
- [ ] Findings include exploit scenario + mitigation.

---

## SRE DONE

- [ ] Reliability impact evaluated.
- [ ] Metrics/logging baseline defined.
- [ ] Failure modes documented.

---

## DEVOPS DONE

- [ ] Merge gates mapped to CI.
- [ ] Release gates identified.
- [ ] Rollback plan documented.
- [ ] Monitoring readiness confirmed.

---

## ORCHESTRATOR DONE

- [ ] Required fields validated.
- [ ] Artifacts verified.
- [ ] Immutable summary generated.
- [ ] Next stage clearly assigned.
- [ ] Loop prevention enforced.

---

## TASK COMPLETION RULE

A task may be marked COMPLETE only when:

1. All relevant role-level DoD items are satisfied.
2. Acceptance criteria are checked PASS.
3. No unresolved critical issues remain.

---

## MACHINE-READABLE FOOTER (REFERENCE)

```json
{
  "definition_of_done_version": 1,
  "status": "complete_or_incomplete",
  "blocking_issues": []
}
```
