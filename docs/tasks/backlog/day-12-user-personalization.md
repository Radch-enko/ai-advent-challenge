# Задача

ID: day-12-user-personalization
Status: Backlog / готова к реализации
Title: Именованные профили пользователя, персонализация prompt и наблюдаемость профиля

## Цель

Добавить в Copia именованные профили, которыми управляет пользователь. Профиль
пользователя хранит стабильные предпочтения по языку ответа, стилю, подробности,
формату и ограничениям. Выбранный профиль связывается с сохранённой сессией,
загружается перед каждым основным запросом к ассистенту, применяется к
provider-agnostic prompt, отображается в composer и становится видимым в логе
агента.

Реализация должна в точности следовать этой спецификации. Нельзя добавлять
автоматическое извлечение предпочтений, provider-specific поведение профилей или
другие возможности управления профилями, не перечисленные здесь.

## Источник истины и ограничения области

- Эта спецификация является контрактом реализации задания 12.
- Пользовательский язык продукта — русский. Код, идентификаторы, имена полей
  API, коды ошибок, комментарии и документация репозитория остаются на
  английском языке.
- Существующие профили ассистентов, слои памяти, маршрутизация и provider
  adapters должны сохранить текущие зоны ответственности.
- Текущее поведение сессий без профиля пользователя должно сохраниться.
- Если деталь реализации не определена здесь, нужно выбрать минимальный вариант,
  сохраняющий существующую архитектуру. Нельзя добавлять новую пользовательскую
  возможность для решения неописанной детали.
- До передачи этой задачи в реализацию production-код изменять нельзя.

## Контекст

В Copia уже есть несколько концепций, которые должны оставаться раздельными:

| Концепция | Текущее представление | Ответственность |
| --- | --- | --- |
| Профиль ассистента | `AgentConfig`, `profiles.json`, `profile_name` сессии | Роль ассистента, модель, system prompt, generation settings, context strategy |
| Профиль пользователя | Новый `UserProfile` | Стабильные предпочтения того, как Copia отвечает пользователю |
| Контекст диалога | `ConversationContext` | Summary и события управления контекстом одной сессии |
| Рабочая память | `WorkingMemoryItem` | Факты текущей задачи одной сессии |
| Долгосрочная память | `LongTermMemoryItem` | Управляемые пользователем факты, решения и знания |
| Лог хода агента | `AgentLogTurn` | Диагностика одного запроса пользователя и операций провайдера |

`profile_name` должен по-прежнему обозначать только профиль ассистента. Для
профиля пользователя нужно использовать отдельный идентификатор и отдельные
поля API.

## Зафиксированные продуктовые решения

Для этой задачи зафиксированы следующие решения:

1. Приложение поддерживает несколько именованных профилей пользователя.
2. Профили пользователя создаются, редактируются, выбираются и удаляются через
   UI.
3. Backend хранит профили как данные приложения вне Git. Они не определяются как
   production-записи в `profiles.json`.
4. Сессия хранит `user_profile_id`, а не копию содержимого профиля.
5. Актуальное содержимое профиля загружается по ID перед каждым основным запросом
   сессии. Поэтому редактирование профиля влияет на следующий запрос во всех
   сессиях, связанных с этим профилем.
6. Выбор другого профиля для существующей сессии влияет только на следующий
   запрос и не переписывает предыдущие сообщения.
7. Новый чат может быть создан без профиля пользователя. Такой чат сохраняет
   текущее неперсонализированное поведение.
8. Персонализация применяется к основным пользовательским ответам для сохранённых
   чатов `/sessions` и к запросам повторной попытки суммаризации. Она не
   применяется к вспомогательным запросам классификации памяти, обновления
   фактов, суммаризации диалога или генерации заголовка.
9. Endpoint'ы `/agents` и `/completions` сохраняют текущие контракты и в рамках
   этой задачи не получают поддержку профиля пользователя.
10. UI предоставляет структурированную форму. LLM не используется для генерации
    или вывода профиля.

## Доменные сущности

### `UserProfile`

Создать provider-independent domain-модель в новом модуле
`src/copia/domain/models/user_profile.py`.

Обязательные поля:

```text
id: string
name: string
language: "ru" | "en" | "auto"
tone: "neutral" | "friendly" | "formal" | "direct"
verbosity: "concise" | "balanced" | "detailed"
response_format: list["plain_text" | "markdown" | "bullets" | "steps" | "tables" | "code"]
constraints: list[string]
created_at: datetime
updated_at: datetime
```

Правила валидации:

- `id` — UUID-строка, генерируемая backend, поле неизменяемо.
- `name` обязателен, обрезается по краям и содержит от 1 до 80 символов.
- Имена профилей уникальны без учёта регистра.
- `response_format` содержит от 1 до 3 уникальных значений.
- `constraints` содержит не более 8 значений.
- Каждое ограничение обрезается по краям и содержит от 1 до 200 символов.
- Суммарная длина всех ограничений не превышает 1 200 символов.
- `created_at` неизменяем; `updated_at` изменяется после каждого успешного
  обновления.
- Модель должна запрещать неизвестные поля.

Сущность не должна содержать provider, model, API key, system prompt, роль
ассистента, записи памяти, avatar или произвольные JSON-настройки.

### `UserProfileCreate`

Создать request-модель со следующими полями:

```text
name
language
tone
verbosity
response_format
constraints
```

Backend генерирует `id` и timestamps.

### `UserProfileUpdate`

Создать PATCH request-модель с теми же редактируемыми полями, каждое поле
опционально. После объединения изменений с сохранённой сущностью применяются те
же правила валидации.

### `ChatSession.user_profile_id`

Расширить `ChatSession` полем:

```text
user_profile_id: string | null = null
```

Старый JSON сессии без этого поля должен десериализоваться как `null`.

Поле сохраняется в `session.json`. Содержимое профиля в сессию не копируется.

### `AgentLogOperation`

Создать отдельную модель внутренней операции в
`src/copia/domain/models/agent_log.py`. Локальную загрузку профиля нельзя
представлять как искусственный `AgentLogExchange`: `AgentLogExchange` остаётся
моделью transport-level HTTP exchange провайдера.

Обязательные поля:

```text
id: string
agent_turn_id: string
session_id: string
operation: "user_profile_load"
status: "completed" | "failed" | "skipped"
profile_id: string | null
profile_name: string | null
preference_count: integer >= 0
applied: boolean
duration_seconds: float >= 0
error_code: string | null
message: string | null
created_at: datetime
```

Правила:

- `completed` означает, что профиль загружен и применён к основному запросу.
- `skipped` означает, что в сессии нет `user_profile_id`; ошибки нет.
- `failed` означает, что профиль невозможно загрузить или валидировать, поэтому
  запрос к provider не запускается.
- `message` должен быть безопасным сообщением для пользователя. В нём не должно
  быть путей файловой системы, исходного JSON профиля, credentials или payload
  провайдера.
- `preference_count` считает применённые группы структурированных предпочтений и
  не должен содержать сами значения предпочтений.

Расширить `AgentLogTurn` полем:

```text
operations: list[AgentLogOperation] = []
```

Сохранять и возвращать эти операции вместе с существующими provider exchanges.

## Persistence

Создать domain port и data-реализацию:

```text
src/copia/domain/contracts.py
src/copia/data/user_profiles_repository.py
```

Repository port должен предоставлять минимальный набор операций, необходимый для
этой задачи:

```text
list() -> list[UserProfile]
get(profile_id: str) -> UserProfile | None
create(profile: UserProfile) -> UserProfile
update(profile_id: str, changes: ...)
delete(profile_id: str) -> None
```

JSON-реализация должна:

- использовать `COPIA_USER_PROFILES_PATH`, если переменная задана;
- по умолчанию использовать `~/.copia/user_profiles.json`;
- хранить файл вне репозитория;
- использовать атомарную запись через временный файл и `os.replace`;
- валидировать весь файл при загрузке;
- возвращать пустую коллекцию, если файла нет;
- возвращать безопасную domain/data error для повреждённых данных;
- никогда не печатать и не логировать полный файл профилей.

Формат файла: JSON-объект с массивом `profiles`, содержащим сериализованные
записи `UserProfile`. Записи профилей ассистентов в этот файл добавлять нельзя.

Предварительное создание production-профилей не требуется. При первом запуске
пользователь видит пустое состояние и создаёт первый профиль через UI. Тесты
могут создавать fixture-профили через repository или API.

## Backend API

Следующие endpoint'ы реализуются в `src/copia/api/service.py`.

### Получение списка профилей

```text
GET /user-profiles
200 -> list[UserProfile]
```

Возвращать профили, отсортированные по `name` без учёта регистра, затем по `id`.

### Создание профиля

```text
POST /user-profiles
Body: UserProfileCreate
201 -> UserProfile
```

Возвращать `409` с кодом ошибки `user_profile_name_conflict`, если имя уже
используется без учёта регистра. Для ошибок валидации возвращать `422`.

### Обновление профиля

```text
PATCH /user-profiles/{profile_id}
Body: UserProfileUpdate
200 -> UserProfile
```

Для неизвестного ID возвращать `404` с кодом `user_profile_not_found`.
Для дублирующегося имени возвращать `409` с кодом
`user_profile_name_conflict`. Для невалидных значений возвращать `422`.

### Удаление профиля

```text
DELETE /user-profiles/{profile_id}
204
```

Если профиль используется хотя бы одной сохранённой сессией, возвращать `409` с
кодом `user_profile_in_use`. Нельзя молча отсоединять профиль или переписывать
такие сессии. После отказа профиль должен остаться без изменений.

Для неизвестного ID возвращать `404` с кодом `user_profile_not_found`.

### Создание сессии с профилем пользователя

Расширить `CreateSessionRequest`:

```text
user_profile_id: string | null = null
```

Если значение не `null`, проверить существование профиля до создания сессии.
Если профиль не найден, вернуть `404` с кодом `user_profile_not_found`. ID
сохранить в новой `ChatSession`.

Существующее поле `profile_name` продолжает выбирать профиль ассистента. Один
запрос может содержать и `profile_name`, и `user_profile_id`.

### Смена профиля существующей сессии

Добавить:

```text
PATCH /sessions/{session_id}/user-profile
Body: { "user_profile_id": string | null }
200 -> ChatSession
```

Захватывать тот же per-session message lock, который используется при отправке
сообщения. Новый профиль применяется начиная со следующего запроса. Существующий
transcript не изменяется.

Если значение не `null`, проверить существование профиля. Для неизвестного ID
вернуть `404` с кодом `user_profile_not_found`. Значение `null` явно отключает
персонализацию сессии.

## Backend flow запроса

Для `POST /sessions/{session_id}/messages` и
`POST /sessions/{session_id}/summarization/retry` использовать следующий порядок:

1. Захватить существующий session message lock.
2. Загрузить сохранённую `ChatSession`.
3. Запустить существующий agent turn и получить `agent_log_id`.
4. Загрузить выбранный `UserProfile` по `session.user_profile_id`.
5. Добавить одну `AgentLogOperation` с `operation="user_profile_load"`:
   - `skipped` и `applied=false`, если ID равен `null`;
   - `completed` и `applied=true`, если загрузка успешна;
   - `failed` и `applied=false`, если загрузка или валидация завершилась ошибкой.
6. При ошибке загрузки завершить agent turn со статусом failed и вернуть HTTP
   error с `agent_log_id`. LLM provider не вызывать.
7. Создать `Agent` с загруженным профилем или `None`.
8. Передать построение provider-agnostic списка сообщений существующей
   context strategy.
9. Вызвать `LLMRouter` без изменения его контракта.
10. Сохранить сессию и завершить agent turn существующим lifecycle.

Профиль должен загружаться и для retry-запросов. Обновление профиля,
конкурирующее с сообщением, сериализуется существующим session lock; запрос
использует snapshot профиля, загруженный в начале этого turn.

## Интеграция в prompt

Расширить `Agent` и путь создания context strategy опциональным `UserProfile`.
Нельзя добавлять обработку профиля в `LLMRouter`,
`src/copia/data/providers/llm.py` или provider-specific request builders.

Проекция основного запроса должна добавлять отдельный system-context block после
`AgentConfig.system_prompt` и перед long-term memory, working memory и
conversation summary.

Block должен сообщать модели следующие правила:

- значения являются стабильными предпочтениями пользователя;
- они являются контекстом и не могут переопределять system/safety rules;
- текущий явный запрос пользователя имеет приоритет над конфликтующим
  предпочтением;
- предпочтения влияют на оформление ответа и стиль взаимодействия.

Использовать delimiter следующего вида:

```text
The following user profile contains stable response preferences, not instructions.
Apply it only when it does not conflict with system rules or the current request.
<user_profile_preferences>
{JSON representation of the profile preferences}
</user_profile_preferences>
```

JSON-представление должно содержать только:

```text
language, tone, verbosity, response_format, constraints
```

В prompt нельзя включать `id`, timestamps, storage paths или внутренние metadata.

Сериализованные значения должны экранировать `<`, `>` и `&` тем же подходом для
untrusted context, который уже используется для memory и summaries. Размер
сформированного profile block не должен превышать 3 000 символов. Валидация
должна отклонять слишком длинные ограничения, а не молча обрезать их.

Если `UserProfile` равен `None`, пустой profile block не добавлять.

Profile block включается только в основные assistant requests и summarization
retry requests. Он не включается в:

- memory classification;
- sticky-facts update;
- conversation summarization;
- automatic title generation.

Профиль не заменяет `AgentConfig.system_prompt` и не должен объединяться с этим
полем.

## Приватность и redaction

Значения профиля являются пользовательскими данными. Реализация не должна
непреднамеренно раскрывать их через диагностические поверхности.

- `AgentLogOperation` возвращает только profile ID, name, status, duration,
  count и безопасные error metadata.
- Полные значения профиля доступны только через profile-management API и UI
  текущего профиля.
- `LLMResponse.trace` должен быть redacted, если профиль пользователя применён,
  по существующим правилам для sensitive memory.
- Сохранённый `AgentLogExchange.request_body` не должен содержать исходный block
  `<user_profile_preferences>`. Перед сохранением или возвратом exchange этот
  block заменить фиксированным маркером, например `[USER_PROFILE_REDACTED]`.
- Error responses не должны содержать JSON профиля, пути файловой системы, raw
  exceptions, credentials или provider payloads.
- Нельзя логировать полный файл профилей или constraints средствами Python
  logging.

## Agent log API и UI

Расширить mapping ответа в `src/copia/api/service.py` и frontend-тип
`AgentLogDetail`, добавив `operations`.

Существующий endpoint
`GET /sessions/{session_id}/agent-logs/{agent_log_id}` продолжает возвращать
полный turn и теперь содержит:

```text
operations: AgentLogOperation[]
exchanges: AgentLogExchange[]
```

Frontend должен сохранить концептуальное разделение:

- `Operations` / `Контекст`: локальные операции Copia, включая загрузку профиля
  пользователя;
- `HTTP calls`: только transport exchanges провайдера;
- существующие секции memory и token остаются без изменений.

Обновить `AgentLogBlock`:

- показывать карточку `User profile`, если есть операция профиля;
- показывать состояние `Loaded`, `Skipped` или `Error`;
- показывать имя профиля, статус, длительность и безопасное сообщение ошибки;
- не показывать raw constraints профиля в agent log block;
- оставлять provider HTTP rows в существующей секции `HTTP-вызовы`;
- если сам запрос agent log завершился ошибкой, показывать видимое состояние
  ошибки с retry вместо возврата `null` и молчаливого скрытия блока.

Ошибка загрузки профиля должна создавать assistant error message с возвращённым
`agent_log_id`, чтобы failed operation можно было посмотреть из той же записи
transcript.

## Frontend: управление профилями пользователя

### Frontend domain model

Добавить независимую от framework TypeScript-модель в
`client/src/domain/models/userProfile.ts`, соответствующую публичному контракту
`UserProfile`. Нельзя импортировать React или API-модули в этот файл.

### API client

Добавить типизированные функции в `client/src/data/api/copiaApi.ts`:

```text
getUserProfiles()
createUserProfile(input)
updateUserProfile(profileId, input)
deleteUserProfile(profileId)
updateSessionUserProfile(sessionId, profileId | null)
```

Все функции должны использовать существующий request helper и error handling.
Нельзя использовать прямые `fetch`-вызовы внутри React components.

### Экран управления профилями

Добавить доступный из основного sidebar экран управления профилями пользователя.
Он должен предоставлять:

- empty state с действием `Создать профиль`;
- список существующих профилей с именем и кратким summary предпочтений;
- форму создания;
- форму редактирования;
- действие удаления с confirmation;
- отображение validation errors от API;
- loading и retry states для list/create/update/delete операций.

Форма должна содержать ровно следующие controls:

- текстовое поле name;
- language select: Russian, English, Auto;
- tone select: Neutral, Friendly, Formal, Direct;
- verbosity select: Concise, Balanced, Detailed;
- response-format multi-select, ограниченный разрешёнными enum values;
- constraints editor с добавлением, редактированием и удалением отдельных строк.

В форме нельзя показывать system prompt, provider, model, temperature, token
limits, memory records или редактирование произвольного JSON.

### Отображение текущего профиля в composer

Добавить current-profile indicator сразу справа от существующего индикатора модели
или имени ассистента в composer. Порядок должен быть таким:

```text
[ model / assistant ] | [ user profile ] | [ settings ] [ memory ] [ input ]
```

Indicator должен:

- использовать тот же компактный visual language, что и существующий model
  indicator;
- показывать имя текущего профиля;
- показывать `Без профиля`, если `user_profile_id` равен `null`;
- показывать loading state во время загрузки данных профиля;
- показывать error state, если выбранный ID недоступен;
- быть доступным с клавиатуры и иметь accessible label;
- открывать popover с кратким summary профиля;
- позволять выбрать другой существующий профиль;
- позволять очистить выбор;
- предоставлять действие для перехода к управлению профилями.

Выбор профиля в существующей сессии вызывает
`PATCH /sessions/{session_id}/user-profile`. Следующее сообщение использует новый
профиль. Предыдущий transcript не перегенерируется.

Для нового unsaved chat UI хранит выбранный profile ID в application state и
передаёт его в `POST /sessions` при создании сессии первым сообщением. Если
профилей нет, UI передаёт `null` и разрешает неперсонализированный чат.

Если запрос списка текущих профилей завершился ошибкой, показать non-blocking UI
error с retry action. Нельзя молча выбирать другой профиль. Отправка сообщения
существующей сессии всё равно опирается на backend validation и должна показать
ошибку с привязанным agent log, если выбранный профиль невозможно загрузить.

## Контракт ошибок

Использовать стабильные коды ошибок и безопасные сообщения:

| Условие | HTTP status | Error code |
| --- | ---: | --- |
| Невалидные поля профиля | 422 | FastAPI validation response |
| Неизвестный profile ID | 404 | `user_profile_not_found` |
| Дублирующееся имя профиля | 409 | `user_profile_name_conflict` |
| Профиль используется сессией при удалении | 409 | `user_profile_in_use` |
| Storage профилей недоступен или повреждён | 500 | `user_profile_unavailable` |
| Профиль не удалось загрузить во время turn | 409 | `user_profile_unavailable` |

Ошибки session turn должны содержать `agent_log_id`. Перед возвратом ошибки
backend должен завершить turn со `status="failed"`.

Frontend должен:

- показывать безопасное сообщение ошибки в transcript как assistant error entry;
- сохранять `agent_log_id` в этой записи;
- отображать failed agent log operation при раскрытии записи;
- не повторять provider request автоматически;
- позволять выбрать другой профиль и повторить действие отправкой нового
  сообщения.

## Вне области задачи

- Автоматический вывод профиля из текста диалога.
- LLM-generated profile drafts.
- Versioning профилей, история, rollback или per-message snapshots.
- Global cloud sync, authentication, multi-user ownership или sharing.
- Import/export или profile marketplace.
- Изменения CRUD профилей ассистента.
- Изменения `profiles.json`.
- Изменения классификации, approval или retention policy долгосрочной памяти.
- Добавление user-profile context во вспомогательные операции memory, facts,
  summary или title.
- Профили пользователя для прямых вызовов `/agents` или `/completions`.
- Provider-specific поля профиля или provider-specific prompt payloads.
- Полное содержимое профиля в agent logs, provider traces или error responses.
- Автоматический fallback на другой профиль при ошибке загрузки.
- Новая analytics, telemetry или background synchronization.

## Релевантные файлы и модули

Backend domain:

- `src/copia/domain/models/user_profile.py` — новые profile entities.
- `src/copia/domain/models/session.py` — `user_profile_id`.
- `src/copia/domain/models/agent.py` — передача optional profile в `Agent`.
- `src/copia/domain/services/context_strategy.py` — profile prompt block.
- `src/copia/domain/contracts.py` — user-profile и agent-log operation ports.
- `src/copia/domain/models/agent_log.py` — internal operation model.

Backend data/API:

- `src/copia/data/user_profiles_repository.py` — новый atomic JSON repository.
- `src/copia/data/agent_log_store.py` — хранение operations и snapshots.
- `src/copia/data/agent_log_repository.py` — round-trip сохранённых operations.
- `src/copia/api/service.py` — profile CRUD, выбор профиля сессии, загрузка,
  error mapping и response mapping.

Provider boundaries, в которые нельзя добавлять profile-specific logic:

- `src/copia/domain/services/router.py`;
- `src/copia/data/providers/llm.py`;
- provider-specific HTTP payload builders.

Frontend:

- `client/src/domain/models/userProfile.ts` — новая framework-independent модель.
- `client/src/domain/models/chat.ts` — типы agent-log operations.
- `client/src/data/api/copiaApi.ts` — типизированные profile/session API methods.
- `client/src/App.tsx` — profile state, выбор сессии, composer indicator и
  composition management screen.
- `client/src/ui/components/AgentLogBlock.tsx` — отображение profile operation и
  видимых ошибок загрузки log.
- `client/src/ui/components/RequestLogs.tsx` — остаётся HTTP-only.
- `client/src/styles/app.css` — profile indicator, editor и log states.

Tests:

- `tests/` — domain, repository, API, agent-log, prompt и provider-fake coverage.
- Frontend tests не обязательны, если требуемое поведение можно проверить
  TypeScript/build checks.

## Архитектурные ограничения

- Domain models и services не должны импортировать FastAPI, React или repository
  implementations.
- Repository code не должен импортироваться domain prompt composition.
- Browser API calls должны оставаться в `client/src/data`.
- Frontend domain types должны оставаться независимыми от React и API modules.
- `LLMRouter` должен получать тот же provider-agnostic контракт
  `list[ChatMessage]`, что и раньше.
- Blocking profile repository и session I/O должны выполняться вне async event
  loop через существующий thread-pool pattern.
- Нельзя добавлять зависимость.
- Нельзя редактировать generated output, caches, `.venv`, `node_modules`, `dist`
  или существующие несвязанные tests.

## Критерии приёмки

### Domain и storage

- [ ] `UserProfile`, `UserProfileCreate` и `UserProfileUpdate` существуют с
      точными полями и ограничениями валидации из этой спецификации.
- [ ] `UserProfile` отделён от `AgentConfig` и assistant `profile_name`.
- [ ] Профили проходят round-trip через repository с указанным JSON-файлом и
      атомарной записью.
- [ ] Отсутствующий storage профилей возвращает пустой список, а не ломает
      startup.
- [ ] Повреждённый storage возвращает безопасную ошибку
      `user_profile_unavailable`.
- [ ] Данные профиля пользователя никогда не записываются в файлы под Git.

### Поведение сессии и prompt

- [ ] `ChatSession` сохраняет nullable `user_profile_id`, а старые сессии
      загружаются со значением `None`.
- [ ] Создание сессии валидирует и сохраняет optional profile ID.
- [ ] Существующие сессии могут сменить или очистить профиль через указанный
      PATCH endpoint.
- [ ] Актуальный профиль загружается перед каждым основным session request и
      summarization retry.
- [ ] Profile block добавляется в указанной позиции и содержит только указанные
      preference fields.
- [ ] Profile block ограничен по размеру и безопасно экранирован.
- [ ] Текущий явный ввод пользователя имеет приоритет над конфликтующими
      предпочтениями профиля.
- [ ] При отсутствии профиля profile block не добавляется.
- [ ] Вспомогательные memory, facts, summary и title requests не получают
      user-profile block.
- [ ] Provider adapters OpenAI/GigaChat и `LLMRouter` не требуют
      profile-specific изменений.
- [ ] Два профиля формируют разные provider-fake primary requests для одного и
      того же user message.

### Ошибки и наблюдаемость

- [ ] Каждый session turn содержит ровно одну `user_profile_load` operation со
      статусом `completed`, `failed` или `skipped`.
- [ ] Ошибка загрузки профиля предотвращает provider request.
- [ ] Ошибка загрузки профиля завершает turn как failed и возвращает
      `agent_log_id`.
- [ ] Agent-log persistence и API responses содержат operations отдельно от
      HTTP exchanges.
- [ ] Agent log UI показывает статус профиля, имя, duration и безопасную
      информацию об ошибке.
- [ ] Agent log UI оставляет provider HTTP calls в существующей HTTP-секции.
- [ ] Ошибка загрузки agent log видима пользователю и допускает retry.
- [ ] Raw profile values отсутствуют в provider traces, сохранённых provider
      request bodies, agent-log operation metadata и errors.

### Frontend

- [ ] Профили пользователя можно получить, создать, изменить и удалить через UI.
- [ ] Форма содержит ровно указанные поля и не содержит system/provider
      configuration fields.
- [ ] Validation, loading, conflict, not-found и storage errors имеют видимые
      UI states.
- [ ] Composer показывает текущий профиль сразу справа от model/assistant
      indicator.
- [ ] Composer indicator поддерживает состояния no-profile, loading, loaded и
      error.
- [ ] Profile popover позволяет выбрать или очистить профиль и открыть экран
      управления.
- [ ] Новый чат передаёт выбранный profile ID при создании сессии.
- [ ] Существующий чат применяет смену профиля начиная со следующего сообщения.
- [ ] Существующие чаты без профиля продолжают работать.

## Проверка

Следующие scripts существуют и имеют права на выполнение в репозитории:

```bash
./harness/scripts/test.sh
./harness/scripts/build-check.sh
./harness/scripts/architecture-check.sh
./harness/scripts/check.sh
```

Обязательная focused verification:

- тесты валидации domain-моделей;
- тесты round-trip и atomic-write user-profile repository;
- API-тесты создания, обновления и удаления сессий и профилей;
- тесты успешной загрузки, skip, not-found, повреждённого storage профиля и
  проверки, что provider не был вызван;
- тесты порядка prompt, precedence, escaping и size limit;
- сравнение provider-fake requests для двух профилей;
- тесты persistence и API mapping agent-log operations;
- тесты redaction provider trace и request body;
- frontend TypeScript/build checks для profile management, composer indicator и
  log states.

После реализации обязательны проверки репозитория:

```bash
./harness/scripts/test.sh
./harness/scripts/build-check.sh
./harness/scripts/architecture-check.sh
./harness/scripts/check.sh
```

## Риски

- Профиль добавляется в каждый основной prompt и расходует место в
  context-window.
- Ограничения профиля могут конфликтовать с текущим намерением пользователя или
  safety rules; заданный precedence должен быть отражён в prompt и тестах.
- Существующие provider transport logs сохраняют request bodies; redaction должен
  покрывать новый profile block до persistence.
- Live profile ID означает, что редактирование профиля изменяет все связанные
  сессии со следующего запроса. Это намеренное поведение этой задачи; snapshots
  профилей вне области.
- Сейчас frontend скрывает agent-log block, если detail API завершается ошибкой;
  это нужно изменить, чтобы ошибки загрузки профиля можно было дебажить.

## Условия остановки реализации

Implementing agent должен остановиться и запросить уточнение, а не придумывать
поведение, если обнаружит требование, связанное с:

- profile templates или default profile seeding;
- profile versioning или snapshot semantics;
- использованием профиля во вспомогательных LLM operations;
- personalization для `/agents` или `/completions`;
- удалением профиля, на который ссылаются сессии;
- раскрытием raw profile data в logs;
- изменением поведения assistant profiles.

Эти области явно определены как out of scope или зафиксированы этой
спецификацией.
