# Задача

ID: finances-api
Status: active
Title: Excel-backed expenses API

## Цель

Добавить в Python/FastAPI backend API для чтения и добавления расходов, хранящихся в
`~/.copia/files/finances.xlsx`.

## Контекст

Файл создаётся пользователем или внешним процессом заранее. Он должен оставаться пригодным для ручного просмотра и
редактирования в Excel. Backend не исправляет и не пересоздаёт отсутствующий или несовместимый файл.

## Функциональные требования

- `GET /expenses` принимает `page_size` от 1 до 100 (по умолчанию 20) и optional opaque `cursor`.
- Расходы возвращаются по `occurred_at` от новых к старым; при равной дате сохраняется порядок строк.
- Ответ содержит `items` и nullable `next_cursor`.
- `POST /expenses` принимает `occurred_at`, `name`, `category`, `amount_rub` и optional `merchant`,
  `payment_method`, `note`, `tags`; возвращает сохранённый расход со сгенерированными `id` и `created_at` и status 201.
- `occurred_at` обязан содержать timezone offset; сумма положительная и имеет не более двух знаков после запятой;
  строки и tags не могут быть пустыми; unknown request fields запрещены.
- Категория является свободным текстом, валюта фиксирована как RUB.

## Нефункциональные требования

- Использовать `openpyxl` и отдельный repository в data layer.
- Ручки синхронные; concurrency control и snapshot pagination не требуются.
- Ошибки имеют `detail.code` и `detail.message` с безопасной конкретной причиной без traceback.

## Вне области задачи

- Создание или автоматическое исправление workbook.
- Доходы, переводы, обновление/удаление расходов, analytics, totals и UI.
- Authentication, authorization, locking и concurrent writes.

## Acceptance criteria

- [ ] Корректный workbook читается постранично в заданном порядке.
- [ ] Новый расход добавляется новой строкой без изменения существующих расходов.
- [ ] Excel использует лист `Expenses`, фиксированные headers и human-readable formatting.
- [ ] Отсутствующий файл возвращает 404; invalid request/cursor — 422; storage/schema failures — 500.
- [ ] Repository и API behavior покрыты focused tests.
- [ ] `./harness/scripts/check.sh` успешно выполнен либо limitation задокументирован.

## Связанные файлы и модули

- `src/copia/domain/models`
- `src/copia/data`
- `src/copia/api/service.py`
- `tests`

## Ограничения

- Python 3.11+, FastAPI, Pydantic v2.
- Sheet `Expenses`; columns строго в порядке: `ID`, `Occurred At`, `Name`, `Category`, `Amount (RUB)`, `Merchant`,
  `Payment Method`, `Note`, `Tags`, `Created At`.
- Timestamps хранятся как RFC 3339 strings, amount — numeric cell, tags — JSON array.

## Проверка

- Focused pytest для expenses repository и API.
- `./harness/scripts/check.sh`.

## Риски

- Offset cursor не обеспечивает snapshot consistency, если workbook изменён между page requests.
- Ручное изменение значений может сделать строку невалидной и недоступной через API до исправления файла.

## Открытые вопросы

Нет.
