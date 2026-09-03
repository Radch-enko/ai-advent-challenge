import json
import os

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.4-mini"
INSTRUCTIONS = """Simulate an expert panel to solve the user's task.

The analyst should solve the task systematically.
The independent solver should propose a solution independently.
The critic should check both solutions, identify mistakes, and recommend an answer.
The judge should use all previous conclusions to choose the final answer.
"""
EXPERT_SCHEMA = {
    "type": "object",
    "properties": {
        "analyst": {
            "type": "object",
            "properties": {"solution": {"type": "string"}},
            "required": ["solution"],
            "additionalProperties": False,
        },
        "independent_solver": {
            "type": "object",
            "properties": {"solution": {"type": "string"}},
            "required": ["solution"],
            "additionalProperties": False,
        },
        "critic": {
            "type": "object",
            "properties": {
                "analysis": {"type": "string"},
                "recommended_answer": {"type": "string"},
            },
            "required": ["analysis", "recommended_answer"],
            "additionalProperties": False,
        },
        "judge": {
            "type": "object",
            "properties": {
                "final_answer": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["final_answer", "reason"],
            "additionalProperties": False,
        },
    },
    "required": ["analyst", "independent_solver", "critic", "judge"],
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

    if not texts:
        raise ValueError("The API response does not contain text output.")

    return "\n".join(texts)


def request_response(task):
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": task,
            "instructions": INSTRUCTIONS,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "expert_panel_result",
                    "strict": True,
                    "schema": EXPERT_SCHEMA,
                },
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def read_user_message():
    return SESSION.prompt("You: ").strip()


def print_result(answer):
    result = json.loads(answer)
    print(f"\nAnalyst:\n{result['analyst']['solution']}")
    print(f"\nIndependent solver:\n{result['independent_solver']['solution']}")
    print(f"\nCritic:\n{result['critic']['analysis']}")
    print(f"\nCritic recommendation:\n{result['critic']['recommended_answer']}")
    print(f"\nJudge:\n{result['judge']['final_answer']}")
    print(f"\nJudge reason:\n{result['judge']['reason']}\n")


load_dotenv()

while True:
    task = read_user_message()

    if not task:
        continue

    if task.lower() in {"exit", "quit"}:
        break

    response_json = request_response(task)

    if response_json["status"] != "completed":
        reason = response_json.get("incomplete_details", {}).get("reason", "unknown")
        print(f"\nAssistant response is incomplete (reason: {reason}).\n")
        continue

    print_result(extract_output_text(response_json))
