from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = OpenAI()
previous_response_id = None

print("Chat started. Press Ctrl+C to stop.")

try:
    while True:
        prompt = input("\nYou: ")

        response = client.responses.create(
            model="gpt-5.4-mini",
            input=prompt,
            previous_response_id=previous_response_id,
        )

        previous_response_id = response.id
        print(f"LLM: {response.output_text}")
except (KeyboardInterrupt, EOFError):
    print("\nChat ended.")
