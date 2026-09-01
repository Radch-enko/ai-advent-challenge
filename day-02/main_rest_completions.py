import os
from pathlib import Path

import requests
from dotenv import load_dotenv


API_URL = "https://api.openai.com/v1/chat/completions"
MAX_COMPLETION_TOKENS = 400
STOP_SEQUENCE = "<END>"
INSTRUCTIONS = (
    "You are a goal-planning assistant. Given a user's goal provide few "
    "concrete, actionable steps. Each step must be one short sentence. Order steps "
    f"by execution sequence. After the fifth step, write {STOP_SEQUENCE} on a new line."
)


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

messages = [{"role": "developer", "content": INSTRUCTIONS}]

print("Chat started. Press Ctrl+C to stop.")

try:
    while True:
        prompt = input("\nYou: ")
        messages.append({"role": "user", "content": prompt})

        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "messages": messages,
                "max_completion_tokens": MAX_COMPLETION_TOKENS,
                "stop": [STOP_SEQUENCE],
            },
            timeout=60,
        )
        if not response.ok:
            print(f"OpenAI API error: {response.status_code}\n{response.text}")
        response.raise_for_status()

        response_json = response.json()
        choice = response_json["choices"][0]
        answer = choice["message"]["content"]
        messages.append({"role": "assistant", "content": answer})

        print(f"LLM: {answer}")
        print(f"Finish reason: {choice['finish_reason']}")
except (KeyboardInterrupt, EOFError):
    print("\nChat ended.")
