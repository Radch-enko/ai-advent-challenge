import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import requests
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings


API_URL = "https://api.openai.com/v1/responses"
MODEL = "gpt-5.4-mini"
TEMPERATURES = [0, 0.7, 1.7]
RUNS_PER_TEMPERATURE = 5
MAX_WORKERS = 5
REPORT_PATH = Path(__file__).with_name("temperature_report.md")
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


def request_response(prompt, temperature):
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "input": prompt,
            "temperature": temperature,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def calculate_metrics(answer, response_json):
    words = re.findall(r"\w+", answer.lower())
    usage = response_json.get("usage", {})
    output_details = usage.get("output_tokens_details", {})

    return {
        "characters": len(answer),
        "words": len(words),
        "lines": len(answer.splitlines()),
        "unique_word_ratio": len(set(words)) / len(words) if words else 0,
        "output_tokens": usage.get("output_tokens"),
        "reasoning_tokens": output_details.get("reasoning_tokens"),
    }


def normalize_answer(answer):
    return " ".join(answer.lower().split())


def average_pairwise_similarity(results):
    if len(results) < 2:
        return None

    similarities = []
    for index, current in enumerate(results):
        for other in results[index + 1 :]:
            similarity = SequenceMatcher(
                None,
                normalize_answer(current["answer"]),
                normalize_answer(other["answer"]),
            ).ratio()
            similarities.append(similarity)

    return sum(similarities) / len(similarities)


def average(results, metric):
    values = [result["metrics"][metric] for result in results]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def format_number(value, digits=1):
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def write_report(prompt, results_by_temperature):
    lines = [
        "# Temperature experiment",
        "",
        f"- Model: `{MODEL}`",
        f"- Runs per temperature: {RUNS_PER_TEMPERATURE}",
        f"- Created: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "## Prompt",
        "",
        "```text",
        prompt,
        "```",
        "",
        "## Summary",
        "",
        "| Temperature | Completed runs | Avg chars | Avg words | Avg output tokens | Avg unique-word ratio | Avg pairwise similarity |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for temperature, results in results_by_temperature.items():
        lines.append(
            "| "
            f"{temperature} | {len(results)} | "
            f"{format_number(average(results, 'characters'))} | "
            f"{format_number(average(results, 'words'))} | "
            f"{format_number(average(results, 'output_tokens'))} | "
            f"{format_number(average(results, 'unique_word_ratio'), 3)} | "
            f"{format_number(average_pairwise_similarity(results), 3)} |"
        )

    lines.extend(
        [
            "",
            "Lower pairwise similarity means the answers are more lexically different. "
            "It does not measure semantic quality or correctness.",
        ]
    )

    for temperature, results in results_by_temperature.items():
        lines.extend(
            [
                "",
                f"## Temperature {temperature}",
                "",
                "| Attempt | Chars | Words | Lines | Output tokens | Reasoning tokens | Unique-word ratio |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for result in results:
            metrics = result["metrics"]
            lines.append(
                "| "
                f"{result['attempt']} | {metrics['characters']} | {metrics['words']} | "
                f"{metrics['lines']} | {format_number(metrics['output_tokens'])} | "
                f"{format_number(metrics['reasoning_tokens'])} | "
                f"{format_number(metrics['unique_word_ratio'], 3)} |"
            )

        for result in results:
            lines.extend(
                [
                    "",
                    f"### Attempt {result['attempt']}",
                    "",
                    "```text",
                    result["answer"],
                    "```",
                ]
            )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_user_message():
    return SESSION.prompt("You: ").strip()


def run_attempt(prompt, temperature, attempt):
    try:
        response_json = request_response(prompt, temperature)

        if response_json["status"] != "completed":
            reason = response_json.get("incomplete_details", {}).get("reason", "unknown")
            return temperature, attempt, None, f"Incomplete response ({reason})."

        answer = extract_output_text(response_json)
        return (
            temperature,
            attempt,
            {
                "attempt": attempt,
                "answer": answer,
                "metrics": calculate_metrics(answer, response_json),
            },
            None,
        )
    except (requests.RequestException, ValueError) as error:
        return temperature, attempt, None, str(error)


load_dotenv()

while True:
    prompt = read_user_message()

    if not prompt:
        continue

    if prompt.lower() in {"exit", "quit"}:
        break

    attempts = [
        (temperature, attempt)
        for temperature in TEMPERATURES
        for attempt in range(1, RUNS_PER_TEMPERATURE + 1)
    ]
    results_by_temperature = {temperature: [] for temperature in TEMPERATURES}

    print(f"Sending {len(attempts)} requests with up to {MAX_WORKERS} workers...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(run_attempt, prompt, temperature, attempt)
            for temperature, attempt in attempts
        ]

        for future in as_completed(futures):
            temperature, attempt, result, error = future.result()

            if error:
                print(f"Temperature {temperature}, attempt {attempt}: {error}")
                continue

            results_by_temperature[temperature].append(result)
            print(f"Temperature {temperature}, attempt {attempt}: completed")

    for results in results_by_temperature.values():
        results.sort(key=lambda result: result["attempt"])

    write_report(prompt, results_by_temperature)
    print(f"\nReport saved to {REPORT_PATH}\n")
