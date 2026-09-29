Prepare the user-facing final answer using exactly the required Russian headings. The answer must focus on the result for the original user request, not on the internal task workflow. Do not describe planning, execution stages, validation statuses, API logs, or subtask progress. Return plain text only; do not use JSON, code fences, or add headings outside the template.

Required template:
## Итоговый ответ

[Direct answer to the user's request. Start with the result.]

### Детали

[Only important details needed to understand or use the answer.]

### Ограничения

[Only limitations that affect the answer, or Нет.]

Original user request:
{{task}}

Internal execution results (use as context, do not reproduce the workflow):
{{steps}}

Internal validation context (do not expose statuses):
Checked steps: {{checked}}
Validation issues: {{issues}}
