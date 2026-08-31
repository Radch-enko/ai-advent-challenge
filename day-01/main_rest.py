import os
from pathlib import Path

import requests
from dotenv import load_dotenv


API_URL = "https://api.openai.com/v1/responses"


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


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

previous_response_id = None

print("Chat started. Press Ctrl+C to stop.")

try:
    while True:
        prompt = input("\nYou: ")
        request_json = {
            "model": "gpt-5.4-mini",
            "input": prompt,
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
        answer = extract_output_text(response_json)
        previous_response_id = response_json["id"]

        print(f"LLM: {answer}")
except (KeyboardInterrupt, EOFError):
    print("\nChat ended.")
