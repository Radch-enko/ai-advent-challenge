import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
MAX_OUTPUT_TOKENS = 1000
INSTRUCTIONS = (
    "You are a goal-planning assistant. Given a user's goal, create exactly five "
    "concrete, actionable steps in execution order. Use Russian for descriptive "
    "fields. Each action must be specific, each success criterion must be verifiable, "
    "and dependencies may reference only earlier step IDs."
)
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_summary": {"type": "string"},
        "goal_category": {
            "type": "string",
            "enum": ["learning", "career", "health", "personal"],
        },
        "recommended_daily_minutes": {
            "type": "integer",
            "minimum": 15,
            "maximum": 240,
        },
        "steps": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "minimum": 1, "maximum": 5},
                    "title": {"type": "string"},
                    "action": {"type": "string"},
                    "duration_minutes": {
                        "type": "integer",
                        "minimum": 5,
                        "maximum": 240,
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                    },
                    "success_criterion": {"type": "string"},
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 1, "maximum": 5},
                        "maxItems": 4,
                    },
                },
                "required": [
                    "id",
                    "title",
                    "action",
                    "duration_minutes",
                    "difficulty",
                    "success_criterion",
                    "depends_on",
                ],
                "additionalProperties": False,
            },
        },
        "weekly_review": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "enum": [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ],
                },
                "question": {"type": "string"},
            },
            "required": ["day", "question"],
            "additionalProperties": False,
        },
        "first_action": {"type": "string"},
    },
    "required": [
        "goal_summary",
        "goal_category",
        "recommended_daily_minutes",
        "steps",
        "weekly_review",
        "first_action",
    ],
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


def extract_output_text(response_json: dict) -> str:
    text_parts = []

    for output_item in response_json["output"]:
        if output_item.get("type") != "message":
            continue

        for content_item in output_item.get("content", []):
            if content_item.get("type") == "output_text":
                text_parts.append(content_item["text"])

    if not text_parts:
        raise ValueError("The API response does not contain text output")

    return "".join(text_parts)


def read_user_message() -> str:
    return SESSION.prompt("You: ").strip()


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

previous_response_id = None

print("Chat started. Press Ctrl+C to stop.")

try:
    while True:
        prompt = read_user_message()

        if not prompt:
            continue

        if prompt.lower() in {"exit", "quit"}:
            break
        request_json = {
            "model": "gpt-5.4-mini",
            "input": prompt,
            "instructions": INSTRUCTIONS,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "goal_plan",
                    "strict": True,
                    "schema": PLAN_SCHEMA,
                }
            },
        }

        if previous_response_id is not None:
            request_json["previous_response_id"] = previous_response_id

        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=request_json,
            timeout=60,
        )
        response.raise_for_status()

        response_json = response.json()
        if response_json["status"] != "completed":
            reason = response_json.get("incomplete_details", {}).get("reason", "unknown")
            print(
                "LLM response is incomplete "
                f"(reason: {reason}). Increase MAX_OUTPUT_TOKENS and try again."
            )
            continue

        answer = extract_output_text(response_json)
        previous_response_id = response_json["id"]

        plan = json.loads(answer)
        print(f"LLM:\n{json.dumps(plan, ensure_ascii=False, indent=2)}")
except (KeyboardInterrupt, EOFError):
    print("\nChat ended.")
