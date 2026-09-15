---
name: expert-council
description: Use when evaluating a non-trivial Copia product, business, architecture, planning, or trade-off decision through the OpenCode subagent Expert Council v3 protocol with a complexity gate, product/business grounding in docs/product, Visionary/Skeptic/Realist/Judge roles, and artifacts saved under docs/reports/expert-council.
---

# Expert Council

Use this skill to run the OpenCode subagent Expert Council v3 protocol for planning, design, architecture, review, or trade-off decisions.

## Complexity gate

The council must not run for every task. Before launching council experts, calculate and record:

```yaml
council_required: true
score: 7
reasons:
  - architectural decision
  - cross-module impact
  - irreversible migration
```

Use this scoring rubric:

| Criterion | Points |
| --- | ---: |
| Public API change | 2 |
| Architectural migration | 2 |
| Security/privacy impact | 3 |
| Multiple equally viable solutions | 2 |
| More than three modules affected | 1 |
| Irreversible decision | 2 |
| High uncertainty | 2 |

Routing thresholds:

- `score < 3`: use a single agent; do not run the council.
- `score 3-5`: use lightweight review; do not run the council.
- `score >= 6`: run the full council.

Important rule: the full Expert Council may run only when `score >= 6`.

## OpenCode council orchestration

The default `orchestrator` must calculate the complexity gate for every user request before normal routing.

When `score >= 6`, the `orchestrator` must run the full Expert Council directly by calling `visionary`, `skeptic`, `realist`, and `council-judge`.

Do not route requests with `score >= 6` to `architect`, `reviewer`, `general`, or the normal delivery loop before the council verdict exists.

The orchestrator must:

- Create `docs/reports/expert-council/<timestamp>-<task-slug>/task.md`.
- Calculate and save the complexity gate result before launching experts.
- Launch `visionary`, `skeptic`, and `realist` only when `score >= 6`.
- Save expert answers only when `score >= 6`.
- Run one critique round only when `score >= 6`.
- Pass all materials to `council-judge` only when `score >= 6`.
- Create `docs/reports/expert-council/<timestamp>-<task-slug>/verdict.md`.

Experts:

- `visionary`: use `openrouter/google/gemini-3-flash-preview`.
- `skeptic`: use `openrouter/deepseek/deepseek-v4-flash`.
- `realist`: use `openrouter/z-ai/glm-5.2`.

All experts and the judge must remain read-only. The orchestrator may edit only council artifacts under `docs/reports/expert-council/**`.

## Product and business context

- Before producing perspectives, inspect relevant product and business documents under `docs/product/`.
- Prefer reading all files in `docs/product/` when the decision affects roadmap, scope, users, positioning, prioritization, monetization, or MVP trade-offs.
- Ground the perspectives, disagreements, critique, and final decision in the product/business information found there.
- If `docs/product/` has no relevant information for the task, state that explicitly in the report and continue from the best available sources.
- Do not invent product or business facts that are not supported by the user request or `docs/product/`.

## Protocol

1. Calculate the complexity gate score.
   - If `score < 3`, route to single-agent handling and do not launch council experts.
   - If `score 3-5`, route to lightweight review and do not launch council experts.
   - If `score >= 6`, continue with the full council.
2. Create the report directory when `score >= 6`, or when the user explicitly invokes `/expert-council`.
3. Save the complexity gate result in `complexity-gate.md` and summarize it in `task.md`.
4. Gather product and business context from `docs/product/`.
5. Produce three independent expert perspectives through `visionary`, `skeptic`, and `realist`.
6. Save expert answers.
7. List disagreements.
8. Run one critique round.
9. Pass all materials to `council-judge`.
10. Produce `verdict.md`.

## Report format

For full council runs, save the result as a markdown artifact set in:

```text
docs/reports/expert-council/<timestamp>-<task-slug>/
```

Use a 4-5 word lowercase hyphenated task slug, for example:

```text
20260727-153012-navigation-state-policy/
```

Required files for every explicit `/expert-council` run and every full council run:

- `task.md`
- `complexity-gate.md`
- `verdict.md`

Required files for a full council run with `score >= 6`:

- `visionary.md`
- `skeptic.md`
- `realist.md`
- `critique.md`
- `judge.md`

`verdict.md` must include:

- `## Complexity Gate`
- `## Decision`
- `## Why This Wins`
- `## Rejected Alternatives`
- `## Product/Business Basis`
- `## Acceptance Criteria`
- `## Follow-up Checks`
- `## Assumptions`
- `## Known Risks`
- `## Confidence`
