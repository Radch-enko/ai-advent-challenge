import os

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.4-mini"
PROMPT_CREATOR_INSTRUCTIONS = (
    "Create a prompt for another model to solve the user's task. "
    "Include all task conditions in the prompt and ask for a correct final answer. "
    "Return only the created prompt, without solving the task yourself."
)
KEY_BINDINGS = KeyBindings()


@KEY_BINDINGS.add("enter")
def send_message(event):
    event.current_buffer.validate_and_handle()


@KEY_BINDINGS.add("escape", "enter")
def insert_newline(event):
    event.current_buffer.insert_text("\n")


SESSION = PromptSession(multiline=True, key_bindings=KEY_BINDINGS)


def extract_output_text(response_json):
    texts = []

    for output in response_json.get("output", []):
        if output.get("type") != "message":
            continue

        for content in output.get("content", []):
            if content.get("type") == "output_text":
                texts.append(content["text"])

    return "\n".join(texts)


def request_response(user_message, instructions=None):
    payload = {
        "model": MODEL,
        "input": user_message,
    }

    if instructions:
        payload["instructions"] = instructions

    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def read_user_message():
    return SESSION.prompt("You: ").strip()


load_dotenv()

while True:
    task = read_user_message()

    if not task:
        continue

    if task.lower() in {"exit", "quit"}:
        break

    prompt_response = request_response(task, PROMPT_CREATOR_INSTRUCTIONS)
    generated_prompt = extract_output_text(prompt_response)
    print(f"\nGenerated prompt:\n{generated_prompt}\n")

    answer_response = request_response(generated_prompt)
    answer = extract_output_text(answer_response)
    print(f"Assistant:\n{answer}\n")
