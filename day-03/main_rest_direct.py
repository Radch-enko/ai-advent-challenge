import argparse
import json
import os

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.4-mini"
SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "schedule": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "string"},
                    "item": {"type": "string"},
                },
                "required": ["slot", "item"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["schedule"],
    "additionalProperties": False,
}
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


def request_response(user_message, previous_response_id=None):
    payload = {
        "model": MODEL,
        "input": user_message,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "schedule",
                "strict": True,
                "schema": SCHEDULE_SCHEMA,
            },
        },
    }

    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

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


def format_schedule(answer):
    schedule = json.loads(answer)
    return "\n".join(
        f"{entry['slot']} — {entry['item']}" for entry in schedule["schedule"]
    )


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format",
        action="store_true",
        help="Print the schedule as readable lines instead of raw JSON.",
    )
    return parser.parse_args()


arguments = parse_arguments()
load_dotenv()
previous_response_id = None

while True:
    user_message = read_user_message()

    if not user_message:
        continue

    if user_message.lower() in {"exit", "quit"}:
        break

    response_json = request_response(user_message, previous_response_id)
    previous_response_id = response_json["id"]

    answer = extract_output_text(response_json)
    output = format_schedule(answer) if arguments.format else answer
    print(f"\nAssistant:\n{output}\n")
