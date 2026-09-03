# Day 02 — control of response length

This REST API chat is based on `day-01/main_rest.py`. It sets a limit of 1000 output tokens with `max_output_tokens` and uses Structured Outputs to return a JSON goal plan with exactly five steps.

`main_rest_completions.py` uses the Chat Completions API with `gpt-4.1-mini`. It applies the same five-step instruction, uses `max_completion_tokens=400`, and stops generation at the `<END>` sequence.

## Run

Run from the repository root after installing the dependencies from Day 01:

```bash
python day-02/main_rest.py
```

To run the Chat Completions version:

```bash
python day-02/main_rest_completions.py
```

The API key must be set in the root `.env` file:

```text
OPENAI_API_KEY=your-api-key
```

Press `Enter` to send a message. Press `Alt+Enter` to add a new line.
