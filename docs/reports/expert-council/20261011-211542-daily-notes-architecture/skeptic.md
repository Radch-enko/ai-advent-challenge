# Skeptic Perspective

## Recommendation

Не принимать решение в текущей формулировке без изменения storage contract. Read-only bind mount — blocker для записи; кроме того, обязательны write-time path security, atomicity, concurrency semantics и защита proxy trust.

## Critical Failure Modes

- запись в `/data/documents/CopiaKnowledgeBase` упадёт из-за `read_only: true`;
- произвольный path от MCP создаёт traversal и symlink/TOCTOU риск;
- concurrent read-modify-write может потерять изменения;
- прямой write без temp file + replace допускает partial corruption;
- ручная индексация оставляет новый текст невидимым RAG до следующего запуска;
- per-call approval может породить approval fatigue в многошаговом edit sequence;
- доверие между MCP proxy и backend должно быть ограничено, а не основано только на URL.

## Rejected Assumptions

Нельзя считать, что MCP server сам имеет доступ к KB; один approval не обязательно покрывает серию изменений; новый файл не сразу доступен RAG; strict Markdown нельзя надёжно делегировать LLM; отсутствие auth между proxy и backend не является безопасным default.

## Minimum Mitigations

Выделенная writable область; server-derived filename; canonical containment and symlink-safe open; atomic write with fsync/replace; per-file lock или эквивалентная optimistic versioning; bounded payload; authenticated/allowlisted proxy; ясная stale-index UX; проверяемый undo/backup или append-only semantics.

## Kill Criteria

Отклонять реализацию без решения read-only blocker, write-time path sanitisation, atomic write и concurrency semantics. Также отклонять, если approval фактически превращается в бездумный accept-all для подшагов.
