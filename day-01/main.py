from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = OpenAI()
previous_response_id = None
KEY_BINDINGS = KeyBindings()


@KEY_BINDINGS.add("enter")
def send_message(event):
    event.current_buffer.validate_and_handle()


@KEY_BINDINGS.add("escape", "enter")
def insert_newline(event):
    event.current_buffer.insert_text("\n")


SESSION = PromptSession(multiline=True, key_bindings=KEY_BINDINGS)


def read_user_message():
    return SESSION.prompt("You: ").strip()


print("Chat started. Press Ctrl+C to stop.")

try:
    while True:
        prompt = read_user_message()

        if not prompt:
            continue

        if prompt.lower() in {"exit", "quit"}:
            break

        response = client.responses.create(
            model="gpt-5.4-mini",
            input=prompt,
            previous_response_id=previous_response_id,
        )

        previous_response_id = response.id
        print(f"LLM: {response.output_text}")
except (KeyboardInterrupt, EOFError):
    print("\nChat ended.")
