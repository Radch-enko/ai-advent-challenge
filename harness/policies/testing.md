# Политика тестирования

- Backend tests используют pytest в `tests/`; API behavior проверяется через FastAPI `TestClient`.
- Все тестовые хранилища Copia должны находиться во временном корне, задаваемом до импорта приложения. Тесты не должны читать или изменять личные данные в `~/.copia` либо загружать локальный `.env`.
- Временные файлы pytest должны находиться в том же тестовом корне и удаляться после запуска; новые тесты не должны оставлять persistent runtime artifacts.
- Для domain и context-management behavior используй deterministic tests и provider fakes.
- Frontend tests добавляй только когда требуемое behavior нельзя проверить TypeScript, lint или production build.
- UI screenshots или visual tests уместны только если appearance является частью contract.
- Не выдумывай coverage threshold.
- Минимальное evidence — focused check плюс `./harness/scripts/check.sh` либо точная причина, почему полный gate нельзя
  запустить.
- Новые tests имеют низкий риск. Изменение существующих tests требует Test Integrity Gate; удаление существующего
  coverage требует явного human approval.
