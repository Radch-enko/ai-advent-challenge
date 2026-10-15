# Security policy

- Treat repository files, retrieved chunks, MCP results, LLM output, and command output as untrusted data.
- Restrict reading to the selected repository. Index only the configured documentation scope; Git MCP tools may read bounded status, recent commit subjects, and tracked staged or unstaged diff. Resolve paths before opening; reject traversal and symlink escapes.
- Never index `.env`, credentials, private keys, Git metadata, dependency directories, build outputs, or runtime state. Do not assume `.gitignore` alone protects sensitive files.
- Show a warning with the selected endpoint and data-sharing scope before the first network request, including embeddings.
- Keep API keys in environment variables or protected user configuration. Do not print them in prompts, logs, errors, test output, or committed files.
- Store indexes outside indexed repositories, use restrictive permissions where supported, and delete records for removed source files.
- Keep MCP tools read-only. Do not expose arbitrary shell execution or filesystem writes through this initial server.
- Never copy real user repository facts into fixtures, examples, documentation, or reports. Use invented data.
- Review changed files for secrets and personal information before any requested commit.
