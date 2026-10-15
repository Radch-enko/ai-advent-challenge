# Git policy

- Preserve unrelated user changes. Never reset, clean, rebase, merge, commit, push, or create branches without an explicit user request.
- Limit changes to the confirmed task or current request.
- Before completion, inspect `git status --short`, `git diff --stat`, and `git diff` when the directory is a Git repository.
- Never commit local credentials, indexes, caches, or generated output.
