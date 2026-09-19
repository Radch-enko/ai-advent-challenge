# Политика Git

- Не создавай branches, commits, pushes, pull requests, merges, rebases, resets, cleans или force operations без явного
  запроса.
- Ограничивай diff подходящей active task или текущим пользовательским запросом.
- Никогда не откатывай несвязанные пользовательские изменения.
- Перед завершением проверяй `git status --short`, `git diff --stat` и `git diff`.
- Generated output и local runtime state нельзя коммитить.
- Используй `harness/templates/commit-message.md`, если явно запрошен task-driven commit.
