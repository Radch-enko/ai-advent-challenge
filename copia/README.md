# Copia

Personal multi-provider AI assistant. Copia supports persistent chats and reusable agent profiles.

## Modules

- `src/copia/domain` — chat, agent, configuration, and routing concepts.
- `src/copia/data` — OpenAI/GigaChat adapters and local session storage.
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

Stop the local API and web client without starting them again:

```bash
./scripts/stop-dev.sh
```

Set at least one provider key in `.env`. The API runs on `http://127.0.0.1:8000`; the web client runs on `http://127.0.0.1:5173`.

## Main components

- `LLMRouter` selects specific adapter for LLM provider for example: Open Ai , Gigachat.
- Every new chat receives an independent session. Its configuration and messages are stored in `~/.copia/sessions/<session-id>/session.json`, outside Git.
- At startup, the API reads these JSON files again; opening a saved chat continues its previous LLM context.
- After the first reply, Copia generates a short title in a separate structured-output request. This request never enters the chat history.
- `AgentFactory` loads named profiles from `profiles.json`.
- Each assistant reply stores the provider-reported input, output, and total token usage. The chat displays these values and compares the latest input plus output with the model limit from `src/copia/data/model_context_windows.json`.
- Context progress updates after a successful response. Unknown models still show their reported usage, but no percentage is calculated.
- The OpenAI context-window catalog was checked against the official model documentation on September 10, 2026. It contains main text model aliases without dated snapshots, plus `gpt-3.5-turbo` for the context-overflow experiment.
