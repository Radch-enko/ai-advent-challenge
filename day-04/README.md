# Day 04 — Temperature

`main_rest_temperature.py` sends the same prompt five times for each temperature: `0`, `0.7`, and `2`.

The script runs up to five requests in parallel. After 15 independent responses, it saves `temperature_report.md` with every answer, per-response metrics, and aggregate statistics for each temperature.

The task and expected calculation are in [task.md](task.md).

## Run

Install the dependencies from Day 01 and set `OPENAI_API_KEY` in the root `.env` file.

```bash
python day-04/main_rest_temperature.py
```

Press `Enter` to send a message. Press `Alt+Enter` to add a new line. Enter `exit` or `quit` to stop the program.
