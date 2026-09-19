# Политика кодирования

- Поддерживай Python 3.11 или новее и размещай packages в `src/copia`.
- Используй Ruff для Python lint и formatting с ограничением длины строки 100 колонок.
- Используй strict checks TypeScript, ESLint и Prettier для React client.
- Предпочитай typed models, прямой control flow и небольшие public interfaces.
- Храни provider-specific behavior в adapters, а browser API calls — в `client/src/data`.
- Делай React effects явными и безопасными с точки зрения зависимостей.
- Добавляй dependencies только для конкретного текущего требования и документируй причину.
- Делай комментарии редкими и полезными.
- Не редактируй generated output, caches, virtual environments, `node_modules`, `dist`, `.run` или `*.egg-info`.
