# Copia

Personal multi-provider AI assistant. Copia supports direct chats with an LLM and independent in-memory agents.

## Modules

- `src/copia/domain` — chat, agent, configuration, and routing concepts.
- `src/copia/data` — OpenAI/GigaChat adapters and future storage adapters.
- `src/copia/api` — FastAPI HTTP endpoints.
- `client` — React + TypeScript web client.
- `profiles.json` — reusable agent templates.
- `client/public/agents` — agent avatar assets.

## Run

```bash
cd copia
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
./scripts/restart-dev.sh
```

Set at least one provider key in `.env`. The API runs on `http://127.0.0.1:8000`; the web client runs on `http://127.0.0.1:5173`.

## Main components

- `LLMRouter` selects specific adapter for LLM provider for example: Open Ai , Gigachat.
- Direct chat calls `/completions` without creating an `Agent`.
- `Agent` owns its configuration and in-memory message history; agent chats use `/agents` and `/agents/{id}/messages`.
- `AgentFactory` loads named profiles from `profiles.json`.
