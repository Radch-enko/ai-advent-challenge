"""Run one prompt against three GigaChat models and save a Markdown report."""

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://api.giga.chat/v1/chat/completions"
OUTPUT_FILE = Path(__file__).with_name("gigachat_results.md")
MAX_TOKENS = 4_000
SCOPE = "GIGACHAT_API_PERS"
KEY_BINDINGS = KeyBindings()


@dataclass(frozen=True)
class ModelConfig:
    name: str
    price_per_million_rub: float


MODELS = (
    ModelConfig("GigaChat-2", 65.00),
    ModelConfig("GigaChat-2-Pro", 500.00),
    ModelConfig("GigaChat-2-Max", 650.00),
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


def get_certificate_bundle() -> Union[bool, str]:
    certificate_path = os.getenv("GIGACHAT_CA_BUNDLE_FILE")
    if not certificate_path:
        return True

    certificate_file = Path(certificate_path).expanduser()
    if not certificate_file.is_file():
        raise RuntimeError(f"Certificate file does not exist: {certificate_file}")
    return str(certificate_file)


def get_access_token(
    authorization_key: str, certificate_bundle: Union[bool, str]
) -> str:
    response = requests.post(
        AUTH_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Basic {authorization_key}",
            "RqUID": str(uuid.uuid4()),
        },
        data={"scope": SCOPE},
        timeout=30,
        verify=certificate_bundle,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def calculate_cost(total_tokens: int, model: ModelConfig) -> float:
    return total_tokens * model.price_per_million_rub / 1_000_000


def run_model(
    model: ModelConfig,
    prompt: str,
    access_token: str,
    certificate_bundle: Union[bool, str],
) -> dict:
    started_at = time.perf_counter()
    response = requests.post(
        CHAT_URL,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "model": model.name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "stream": False,
        },
        timeout=600,
        verify=certificate_bundle,
    )
    elapsed_seconds = time.perf_counter() - started_at
    response.raise_for_status()

    response_json = response.json()
    usage = response_json["usage"]
    return {
        "model": model.name,
        "elapsed_seconds": elapsed_seconds,
        "input_tokens": usage["prompt_tokens"],
        "output_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "cost_rub": calculate_cost(usage["total_tokens"], model),
        "answer": response_json["choices"][0]["message"]["content"],
    }


def format_report(prompt: str, results: list[dict]) -> str:
    lines = [
        "# GigaChat model comparison results",
        "",
        f"Run at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Metrics",
        "",
        "| Model | Time, s | Input tokens | Output tokens | Billable tokens | Cost, RUB |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        lines.append(
            "| {model} | {elapsed_seconds:.2f} | {input_tokens} | {output_tokens} | "
            "{total_tokens} | ₽{cost_rub:.4f} |".format(**result)
        )

    lines.extend(["", "## Prompt", "", prompt, "", "## Answers"])
    for result in results:
        lines.extend(["", f"### {result['model']}", "", result["answer"]])
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    authorization_key = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
    if not authorization_key:
        raise RuntimeError(
            "Set GIGACHAT_AUTHORIZATION_KEY in the root .env file before running"
        )

    print("Press Enter to run the comparison. Press Alt+Enter to add a line.")
    prompt = read_prompt()
    if not prompt:
        raise RuntimeError("Prompt cannot be empty")

    certificate_bundle = get_certificate_bundle()
    access_token = get_access_token(authorization_key, certificate_bundle)
    results = []
    for model in MODELS:
        print(f"Running {model.name}...")
        result = run_model(model, prompt, access_token, certificate_bundle)
        results.append(result)
        print(
            f"  {result['elapsed_seconds']:.2f}s, "
            f"{result['total_tokens']} billable tokens, ₽{result['cost_rub']:.4f}"
        )

    OUTPUT_FILE.write_text(format_report(prompt, results), encoding="utf-8")
    print(f"Saved report to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
