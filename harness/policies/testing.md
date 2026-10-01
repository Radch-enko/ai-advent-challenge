# Политика тестирования

- Backend tests используют pytest в `tests/`; API behavior проверяется через FastAPI `TestClient`.
- Все тестовые хранилища Copia должны находиться во временном корне, задаваемом до импорта приложения. Тесты не должны читать или изменять личные данные в `~/.copia` либо загружать локальный `.env`.
- Все тексты примеров, реплики, fixtures, snapshots и expected values в tests и evals должны быть вымышленными и
  создаваться специально для проверки. Не используй сведения из персональной базы знаний, профиля, реальных диалогов
  или локальных пользовательских файлов, даже если меняешь имена или слегка перефразируешь текст.
- Перед завершением изменения тестов проверяй diff, включая staged, unstaged и untracked файлы, на реальные
  пользовательские факты. Используй очевидно демонстрационные значения и зарезервированные placeholders вроде
  `user@example.invalid`, когда нужны адреса.
- Временные файлы pytest должны находиться в том же тестовом корне и удаляться после запуска; новые тесты не должны оставлять persistent runtime artifacts.
- Для domain и context-management behavior используй deterministic tests и provider fakes.
- Frontend tests добавляй только когда требуемое behavior нельзя проверить TypeScript, lint или production build.
- UI screenshots или visual tests уместны только если appearance является частью contract.
- Не выдумывай coverage threshold.
- Минимальное evidence — focused check плюс `./harness/scripts/check.sh` либо точная причина, почему полный gate нельзя
  запустить.
- Новые tests имеют низкий риск. Изменение существующих tests требует Test Integrity Gate; удаление существующего
  coverage требует явного human approval.
