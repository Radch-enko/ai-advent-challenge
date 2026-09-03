# Day 03 — Reasoning approaches

The task and expected answer are in [task.md](task.md).

- Direct answer: use `main_rest_direct.py`. It uses Structured Outputs to return only a schedule of up to 20 entries.
- Step-by-step answer: use `main_rest_step_by_step.py`.
- Generated-prompt answer: use `main_rest_generated_prompt.py`.
- Expert-panel answer: use `main_rest_expert_group.py`.

`main_rest_step_by_step.py` uses the same Responses API request as Day 01, but adds an `instructions` field that asks the model to show its reasoning before the final answer.

`main_rest_generated_prompt.py` makes two API requests: the first creates a prompt for solving the task, and the second uses that prompt to produce an answer.

`main_rest_expert_group.py` makes one API request. It asks the model to simulate an analyst, an independent solver, a critic, and a judge.

## Run

Set `OPENAI_API_KEY` in the root `.env` file and install the dependencies from `day-01/requirements.txt`.

```bash
python day-03/main_rest_step_by_step.py
```

Press `Enter` to send a message. Press `Alt+Enter` to add a new line. Enter `exit` or `quit` to stop the program.

To see the direct answer as readable schedule lines instead of raw JSON, run:

```bash
python day-03/main_rest_direct.py --format
```

To generate a prompt first and then solve the task with it, run:

```bash
python day-03/main_rest_generated_prompt.py
```

To solve a task through the expert panel, run:

```bash
python day-03/main_rest_expert_group.py
```
