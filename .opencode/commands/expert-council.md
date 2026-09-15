---
description: Run the Expert Council complexity gate, save artifacts, and launch the full council only when required.
agent: orchestrator
---

Run the Expert Council protocol for this decision:

```text
$ARGUMENTS
```

Use the OpenCode subagent council protocol from `.agents/skills/expert-council/SKILL.md`.

Create a run directory under:

```text
docs/reports/expert-council/<timestamp>-<task-slug>/
```

First calculate and save `complexity-gate.md`:

```yaml
council_required: true
score: 7
reasons:
  - architectural decision
  - cross-module impact
  - irreversible migration
```

Route by score:

- `score < 3`: single agent; do not launch the council.
- `score 3-5`: lightweight review; do not launch the council.
- `score >= 6`: full council.

Important: launch `visionary`, `skeptic`, `realist`, and `council-judge` directly from the orchestrator only when `score >= 6`.

Always create `task.md`, `complexity-gate.md`, and `verdict.md`. For `score < 6`, `verdict.md` must explain why the full council was not launched and which lighter route should be used. For `score >= 6`, launch `visionary`, `skeptic`, and `realist`, save their answers, run one critique round, pass all materials to `council-judge`, and write `verdict.md`.

All experts and the judge must remain read-only. Ground product and business reasoning in the user request, `AGENTS.md`, `README.md`, and `docs/product/` when present. Do not edit application code. Do not commit or push.
