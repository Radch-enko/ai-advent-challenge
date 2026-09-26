# Copia

Personal multi-provider AI assistant. Copia supports persistent chats and reusable agent profiles.

## Modules

- `src/copia/<feature>/domain` — chat, agent, configuration, and routing concepts.
- `src/copia/<feature>/data` — provider adapters and local storage.
- `src/copia/<feature>/api` — FastAPI HTTP endpoints; `src/copia/service.py` assembles the app.
- `client` — React + TypeScript web client.
- `profiles.json` — reusable agent templates.
- `client/public/agents` — agent avatar assets.

## Run

```bash
./harness/scripts/check-dependencies.sh
cp .env.example .env
./scripts/restart-dev.sh
```

Stop the local API and web client without starting them again:

```bash
./scripts/stop-dev.sh
```

Set at least one provider key in `.env`. The API runs on `http://127.0.0.1:8000`; the web client runs on `http://127.0.0.1:5173`.

Persistent data uses `~/.copia` by default. Set `COPIA_DATA_ROOT` to use a different data directory; existing per-store path overrides still take precedence.

## Scheduled expense summaries

Copy [`schedules.example.json`](schedules.example.json) to `~/.copia/schedules.json` and restart the API. The example runs a current-day expense summary every minute and a completed-week summary every Monday at midnight in `Asia/Omsk`. Calendar schedules use an IANA timezone, a `HH:MM` local time, and an optional `day_of_week` (`mon` through `sun`). Interval schedules use `minutes`. `report_period: {"type": "current_day", "timezone": "Asia/Omsk"}` makes every run cover local midnight through the actual execution time; without `report_period`, the report covers consecutive planned runs. Only enabled jobs run. The optional `name` appears in the summary screen; otherwise the job ID is shown. The accountant profile must have an MCP connection offering `search_expenses`.

The API activates a new or changed schedule at startup. After a later restart it runs at most the latest missed interval; it does not replay every missed period. Each run is saved atomically in `~/.copia/scheduled-runs/<job-id>/`, with the latest 50 retained. `~/.copia/scheduler-state.json` records activation and the last processed slot. The “Сводки” screen shows each enabled job's status and time until its next planned run, plus the latest completed agent answer as Markdown and any failure from the latest run. The screen uses `react-markdown` and `remark-gfm` for report headings, lists, and tables without rendering raw HTML. The backend scheduler assumes one API process.

The config, state, and run paths can be overridden with `COPIA_SCHEDULES_PATH`, `COPIA_SCHEDULER_STATE_PATH`, and `COPIA_SCHEDULED_RUNS_PATH`.

## Main components

- `LLMRouter` selects specific adapter for LLM provider for example: Open Ai , Gigachat.
- Every new chat receives an independent session. Its configuration and messages are stored in `~/.copia/sessions/<session-id>/session.json`, outside Git.
- At startup, the API reads these JSON files again; opening a saved chat continues its previous LLM context.
- After the first reply, Copia generates a short title in a separate structured-output request. This request never enters the chat history.
- `AgentFactory` loads named profiles from `profiles.json`.
- Each assistant reply stores the provider-reported input, output, and total token usage. The chat displays these values and compares the latest input plus output with the model limit from `src/copia/providers/data/model_context_windows.json`.
- Context progress updates after a successful response. Unknown models still show their reported usage, but no percentage is calculated.
- Context compression keeps the full transcript for the UI while sending the LLM an evolving summary plus recent original messages. The summary prompt, provider, model, generation settings, number of recent user-assistant pairs, and summary batch size in pairs are configurable per chat or agent.
- Sliding Window keeps the full transcript in the session and UI, but sends only the latest configured number of transcript messages to the LLM. The system prompt does not count toward this limit.
- Sticky Facts runs a structured memory update after every user message, stores the resulting key-value memory in `facts.json` beside the session file, and sends those facts plus the latest configured number of transcript messages to the main LLM.
- Global Copia invariants are user-managed binding rules stored in `~/.copia/invariants.json`, separately from chat transcripts. They are included in every LLM request, including new chats, agents, completions, and task mode, and conflicting requests should receive an explicit refusal with a compliant alternative when possible.
- Branching can fork any persisted message into a new independent session. The new session receives the transcript up to that message and sends its complete copied history to the LLM.
- Summarization is completed before the main assistant response. Its status and API logs appear in the transcript; a failed pass blocks new messages until Retry succeeds and resumes the pending turn.
- The OpenAI context-window catalog was checked against the official model documentation on September 10, 2026. It contains main text model aliases without dated snapshots, plus `gpt-3.5-turbo` for the context-overflow experiment.
