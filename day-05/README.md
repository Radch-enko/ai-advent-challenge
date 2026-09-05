# Day 05 — model versions

`compare_models.py` sends the same user-entered prompt to three OpenAI models:

- `gpt-5.6-luna` — weak / inexpensive;
- `gpt-5.6-terra` — middle tier;
- `gpt-5.6-sol` — strongest tier.

For each response it measures wall-clock time, reads token usage from the Responses API, and calculates the cost from the published per-token prices. The resulting `results.md` contains the table, prompt, and all three answers for a qualitative comparison.

## Token prices

Standard API prices per 1 million text tokens:

| Model | Input | Output |
| --- | ---: | ---: |
| `gpt-5.6-luna` | $0.20 | $1.20 |
| `gpt-5.6-terra` | $2.00 | $12.00 |
| `gpt-5.6-sol` | $4.00 | $20.00 |

The script calculates each request as `(input tokens × input price + output tokens × output price) / 1,000,000`. This is why a reasoning model's invisible reasoning tokens still affect the cost: they are included in the API's `output_tokens` field.

`MAX_OUTPUT_TOKENS` is set to 4,000 in the script. This is a shared ceiling for all models, and it includes both the visible answer and internal reasoning tokens. A lower limit can finish the response prematurely with `max_output_tokens`, as happened with 700 tokens.

## Run

The root `.env` file must contain:

```text
OPENAI_API_KEY=your-api-key
```

Install the dependencies from Day 01, then run from the repository root:

```bash
python day-05/compare_models.py
```

Enter one prompt in the terminal. `Enter` starts the comparison; `Alt+Enter` adds a new line. The identical entered text is sent to every model.

## GigaChat comparison

`compare_gigachat_models.py` uses the GigaChat REST API to run the same prompt through the current GigaChat 2 tiers:

- `GigaChat-2` — Lite, the weakest and least expensive model;
- `GigaChat-2-Pro` — the middle tier;
- `GigaChat-2-Max` — the strongest tier.

Create an authorization key in the GigaChat API dashboard and add it to the root `.env` file:

```text
GIGACHAT_AUTHORIZATION_KEY=your-authorization-key
```

This is the key used to obtain a short-lived OAuth access token; it is not the access token itself. The script obtains a fresh token, runs each model, and saves `day-05/gigachat_results.md`.

```bash
python day-05/compare_gigachat_models.py
```

GigaChat charges for all billable tokens at one price per model. The API returns them in `usage.total_tokens` after cached tokens are excluded, so the script calculates `total_tokens × price / 1,000,000`.

| Model | Price per 1M billable tokens |
| --- | ---: |
| `GigaChat-2` (Lite) | ₽65 |
| `GigaChat-2-Pro` | ₽500 |
| `GigaChat-2-Max` | ₽650 |

GigaChat requires the Russian Ministry of Digital Development root certificate. You can install it into the active virtual environment's `certifi` bundle using the [official GigaChat command](https://developers.sber.ru/docs/ru/gigachat/certificates). Alternatively, save the PEM file locally and set its absolute path in `.env`:

```text
GIGACHAT_CA_BUNDLE_FILE=/absolute/path/to/russian_trusted_root_ca_pem.crt
```

The script passes this file to `requests` as the CA bundle for both OAuth and model requests. Do not disable TLS verification.

The macOS system Python 3.9 bundled with Xcode uses LibreSSL 2.8.3, which is not supported by `urllib3` 2.x. This repository therefore pins `urllib3<2`; after updating the project, reinstall the dependencies in the active virtual environment before running the GigaChat script.

Official references: [authentication](https://developers.sber.ru/docs/ru/gigachat/api/reference/rest/gigachat-api), [models and prices](https://developers.sber.ru/docs/ru/gigachat/models/gigachat-2-lite), and [token accounting](https://developers.sber.ru/docs/ru/gigachat/guides/counting-tokens).

## GigaChat experiment results

Four single-run prompts were compared: logical reasoning, Kotlin code review, Kotlin code generation, and a creative marketing task. The source reports are `gigachat_results-logic-explanation.md`, `gigachat_results_find_errors_in_code.md`, `gigachat_results-generate-code.md`, and `gigachat_results.md`.

### Quality of answers

| Task | GigaChat-2 (Lite) | GigaChat-2-Pro | GigaChat-2-Max |
| --- | --- | --- | --- |
| Logic | Explains the false premise, but inconsistently calls the argument invalid while also recognising its valid form. | Correctly distinguishes the argument's form from the factual truth of its premise. | Gives the clearest and most precise distinction between validity and truth. |
| Kotlin code review | The proposed fix still does not compile: `Task.copy()` requires a data class. It also identifies a valid lambda syntax as an error. | Finds several real errors, but retains invalid `synchronized fun` in the final code. | Finds the important compilation errors and provides the only runnable final version of the three. |
| Kotlin code generation | Works for a parseable ISO date, but has no invalid-input handling. | Concise and idiomatic because it accepts `LocalDate`, but delegates parsing to the caller. | Most robust answer: documents a date format and handles parse errors. |
| Creative task | Delivers all requested parts, but the promotion is generic and commercially over-generous. | More coherent campaign with a clear audience and goal. | Most concise and locally relevant offer with clear conditions. |

All three models interpreted “older than 18” as `>= 18`. Strictly speaking, a person exactly 18 years old does not satisfy “older than 18”, so this shared issue is a useful reminder to assess requirement interpretation separately from code style.

**Quality conclusion:** Max was consistently strongest on tasks with several interacting requirements, especially code review. Pro was close on reasoning and produced useful answers, but missed a compilation blocker in its code-review fix. Lite was sufficient for simple or creative responses, but made more technical mistakes.

### Speed and resource usage

Average values across the four runs:

| Model | Average time, s | Average billable tokens | Average cost, RUB |
| --- | ---: | ---: | ---: |
| GigaChat-2 (Lite) | 2.78 | 490 | ₽0.0318 |
| GigaChat-2-Pro | 5.55 | 445 | ₽0.2225 |
| GigaChat-2-Max | 6.37 | 495 | ₽0.3216 |

**Speed conclusion:** Lite was about twice as fast as Pro and 2.3 times faster than Max. Pro and Max had comparable latency on the creative request, but Max was slower on the reasoning and code tasks.

**Resource conclusion:** token consumption did not grow consistently with model tier: Pro used the fewest billable tokens on average, while Lite and Max were almost equal. Cost grew primarily because of the higher per-token tariff, not because Max always generated more tokens. In these runs, Pro cost about seven times more than Lite, and Max about ten times more.

These are exploratory measurements, not a benchmark: each task was run once, and wall-clock time includes network latency and server load. Repeating every prompt several times would make the latency comparison more reliable.

## Prompts for comparison

Use the same prompt in a separate run for each task type. Do not ask models to browse the web: then you compare their reasoning and instruction following, not the freshness of external data.

### 1. Constraints and reasoning

```text
У Анны, Бориса и Веры разные должности: аналитик, дизайнер и менеджер.
Известно, что Анна не менеджер; дизайнер не Борис; Вера не аналитик;
менеджер старше дизайнера. Анне 28, Борису 35, Вере 31 год.
Определи должность каждого. Покажи ход рассуждений и проверь, что все условия выполнены.
```

Compare correctness, whether the model notices ambiguity or contradiction, and whether its stated reasoning actually supports the conclusion.

### 2. Code review and debugging

```text
Найди все ошибки в этом Python-коде и предложи минимальное исправление.
Объясни, почему каждая ошибка проявляется.

def average_positive(numbers):
    total = 0
    count = 0
    for number in numbers:
        if number >= 0:
            total += number
        count += 1
    return total / count

print(average_positive([-2, 0, 4]))
print(average_positive([-2, -1]))
```

Compare whether the answer finds the incorrect `count` update and the division-by-zero case, and whether the proposed fix is minimal and runnable.

### 3. Product and engineering trade-offs

```text
Нужно добавить офлайн-режим в приложение доставки еды за две недели.
Пользователь должен видеть последнюю синхронизированную корзину и историю заказов,
но не должен оформлять новый заказ без сети. Предложи минимальный технический план:
данные для локального хранения, стратегию синхронизации, обработку конфликтов и
три риска. Не используй новые серверные API без явной необходимости.
```

Compare completeness, realistic prioritisation within the deadline, explicit trade-offs, and absence of unjustified assumptions.

## Notes

- The timer includes network latency and OpenAI processing time; it does not measure the model's isolated inference time.
- `output_tokens` includes any reasoning tokens billed by the API, so the cost calculation reflects the API usage more accurately than counting visible answer words.
- Prices in the script are current standard prices at the time it was written. Update `MODELS` before rerunning if the pricing changes.
- `gpt-5.6-sol` is intentionally included as the strongest model. It costs more and can take longer on difficult prompts.

## Official references

- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra)
- [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
