# Task Compression Layer (Immutable Summary)

Purpose:
- Keep context small and stable across many agent hops.
- Prevent context window blowups.
- Make handoffs deterministic.

Rules:
- MUST be short (5-10 lines max).
- MUST be factual (no speculation).
- MUST mention exact artifacts (file paths, commands).
- MUST list open risks/questions.
- MUST include next stage and what they must do.

---

## REQUIRED COMPRESSION OUTPUT FORMAT

### IMMUTABLE SUMMARY (5-10 lines)
1) Task: <task_id> - <one-line goal>
2) Changes/Artifacts: <files/links>
3) Validation: <commands/tests run + result>
4) Acceptance: <what is met / not met>
5) Risks: <top 1-3>
6) Open questions: <if any>
7) Next: <next role + action list>

### MACHINE-READABLE FOOTER (REQUIRED)

```json
{
  "task_id": "",
  "type": "compression_summary",
  "artifacts": [],
  "validation": [],
  "acceptance_status": "unknown|partial|met|not_met",
  "risks": [],
  "open_questions": [],
  "next_owner": "",
  "next_actions": []
}
```
