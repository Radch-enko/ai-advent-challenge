# Git Policy

- Do not create branches, commits, pushes, pull requests, merges, rebases, resets, cleans, or force operations unless explicitly requested.
- Keep diffs scoped to the matching active task or current user request.
- Never revert unrelated user changes.
- Review `git status --short`, `git diff --stat`, and `git diff` before completion.
- Generated output and local runtime state must not be committed.
- Use `harness/templates/commit-message.md` when a task-driven commit is explicitly requested.
