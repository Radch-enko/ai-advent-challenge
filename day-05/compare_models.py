"""Run one prompt against three OpenAI models and save a Markdown report."""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
OUTPUT_FILE = Path(__file__).with_name("results.md")
# This limit covers both visible text and reasoning tokens.
MAX_OUTPUT_TOKENS = 4_000
KEY_BINDINGS = KeyBindings()


@dataclass(frozen=True)
class ModelConfig:
    name: str
    input_price_per_million: float
    output_price_per_million: float


MODELS = (
    ModelConfig("gpt-5.6-luna", 0.20, 1.20),
    ModelConfig("gpt-5.6-terra", 2.00, 12.00),
    ModelConfig("gpt-5.6-sol", 4.00, 20.00),
)


@KEY_BINDINGS.add("enter")
def send_prompt(event):
    event.current_buffer.validate_and_handle()


@KEY_BINDINGS.add("escape", "enter")
def insert_newline(event):
    event.current_buffer.insert_text("\n")


SESSION = PromptSession(multiline=True, key_bindings=KEY_BINDINGS)


def read_prompt() -> str:
    return SESSION.prompt("Prompt: ").strip()


def extract_output_text(response_json: dict) -> str:
    parts = []
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content["text"])

    if not parts:
        raise ValueError("The API response does not contain text output")
    return "".join(parts)


def calculate_cost(usage: dict, model: ModelConfig) -> float:
    input_tokens = usage["input_tokens"]
    output_tokens = usage["output_tokens"]
    return (
        input_tokens * model.input_price_per_million
        + output_tokens * model.output_price_per_million
    ) / 1_000_000


def run_model(model: ModelConfig, prompt: str, api_key: str) -> dict:
    started_at = time.perf_counter()
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model.name,
            "input": prompt,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
        timeout=600,
    )
    elapsed_seconds = time.perf_counter() - started_at
    response.raise_for_status()

    response_json = response.json()
    if response_json.get("status") != "completed":
        reason = response_json.get("incomplete_details", {}).get("reason", "unknown")
        raise RuntimeError(f"{model.name}: response is incomplete ({reason})")

    usage = response_json["usage"]
    return {
        "model": model.name,
        "elapsed_seconds": elapsed_seconds,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
        "cost_usd": calculate_cost(usage, model),
        "answer": extract_output_text(response_json),
    }


def format_report(prompt: str, results: list[dict]) -> str:
    lines = [
        "# Model comparison results",
        "",
        f"Run at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Metrics",
        "",
        "| Model | Time, s | Input tokens | Output tokens | Total tokens | Cost, USD |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            "| {model} | {elapsed_seconds:.2f} | {input_tokens} | {output_tokens} | "
            "{total_tokens} | ${cost_usd:.6f} |".format(**result)
        )

    lines.extend(["", "## Prompt", "", prompt, "", "## Answers"])
    for result in results:
        lines.extend(["", f"### {result['model']}", "", result["answer"]])
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY in the root .env file before running")

    print("Press Enter to run the comparison. Press Alt+Enter to add a line.")
    prompt = read_prompt()
    if not prompt:
        raise RuntimeError("Prompt cannot be empty")

    results = []
    for model in MODELS:
        print(f"Running {model.name}...")
        result = run_model(model, prompt, api_key)
        results.append(result)
        print(
            f"  {result['elapsed_seconds']:.2f}s, "
            f"{result['total_tokens']} tokens, ${result['cost_usd']:.6f}"
        )

    OUTPUT_FILE.write_text(format_report(prompt, results), encoding="utf-8")
    print(f"Saved report to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
