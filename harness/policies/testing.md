# Политика тестирования

- Backend tests используют pytest в `tests/`; API behavior проверяется через FastAPI `TestClient`.
- Для domain и context-management behavior используй deterministic tests и provider fakes.
- Frontend tests добавляй только когда требуемое behavior нельзя проверить TypeScript, lint или production build.
- UI screenshots или visual tests уместны только если appearance является частью contract.
- Не выдумывай coverage threshold.
- Минимальное evidence — focused check плюс `./harness/scripts/check.sh` либо точная причина, почему полный gate нельзя
  запустить.
- Новые tests имеют низкий риск. Изменение существующих tests требует Test Integrity Gate; удаление существующего
  coverage требует явного human approval.
