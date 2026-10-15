# Architecture policy

- Keep command-line parsing and presentation separate from application behavior.
- Keep repository access, index persistence, MCP transport, and LLM HTTP at explicit boundaries. Application and retrieval logic must not import OpenAI SDK models.
- Define small interfaces only where current behavior needs substitution in tests or later provider replacement: chat generation and embeddings are separate capabilities.
- Keep repository and provider adapters replaceable without a generic plugin framework or provider registry.
- Retrieve documentation with embeddings and attach verifiable path and position metadata to every chunk.
- Indexes are scoped to a resolved repository identity and embedding model. Do not mix vectors from different models or dimensions.
- Git context crosses an actual MCP client/server boundary and remains read-only.
- Do not build support for file edits, autonomous shell commands, or additional providers until requested.
