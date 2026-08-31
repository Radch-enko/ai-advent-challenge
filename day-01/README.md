# Day 01 — первый запрос к LLM

Два минимальных CLI-чата на Python, которые отправляют сообщения в OpenAI Responses API, сохраняют контекст диалога и выводят ответы модели в консоль:

- `main.py` использует официальный OpenAI SDK;
- `main_rest.py` выполняет REST-запрос напрямую через универсальную HTTP-библиотеку `requests`.

## Запуск

Команды выполняются из корня репозитория:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r day-01/requirements.txt
python day-01/main.py
```

Для запуска REST-версии:

```bash
python day-01/main_rest.py
```

Диалог продолжается, пока работает процесс. Для завершения нажмите `Ctrl+C` или `Ctrl+D`.

API-ключ должен находиться в корневом файле `.env`:

```text
OPENAI_API_KEY=your-api-key
```
