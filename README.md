# Vartovyi

Сервіс моніторингу доступності сайтів і API: періодично перевіряє задані URL,
рахує uptime, відкриває й закриває інциденти та показує публічну сторінку
статусу. Навчальний аналог UptimeRobot на FastAPI і async Python.

## Можливості

- Реєстрація та вхід на JWT (access + refresh з ротацією), відкликання токенів
  через чорний список `jti` у Redis, API-ключі для скриптів і CI
- CRUD моніторів з пагінацією, фільтрами, сортуванням і ізоляцією за власником
- Асинхронний рушій перевірок: `TaskGroup` + `Semaphore`, окремий
  `asyncio.timeout()` на кожну перевірку, один `httpx.AsyncClient` на процес
- Оцінка відповіді: очікуваний статус, ключове слово в тілі, поріг деградації
- Інциденти: відкриваються після N падінь поспіль, закриваються першою успішною
  перевіркою
- Публічна сторінка статусу `/status/{slug}` з uptime за 24 год, 7 і 30 днів
- Request id, JSON-логи, єдиний формат помилок для всього API

## Стек

FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, PostgreSQL,
Redis, httpx, PyJWT, passlib[bcrypt], uv, pytest + respx, ruff, mypy --strict.

## Архітектура

Шари залежать лише від нижчих. Домен не імпортує жодного фреймворку, тож його
правила тестуються без БД і мережі.

```mermaid
flowchart TD
    client([HTTP-клієнт]) --> mw[Middleware<br/>request id, timing, логи, 500]
    mw --> api[api/v1/endpoints<br/>маршрути, залежності, exception handlers]
    api --> schemas[schemas<br/>Pydantic Create / Update / Read]
    api --> services[services<br/>сценарії, межі транзакцій]
    services --> repos[repositories<br/>запити до БД і Redis, без commit]
    services --> domain[domain<br/>чисті правила і помилки]
    repos --> models[db/models<br/>SQLAlchemy 2.0]
    models --> pg[(PostgreSQL)]
    repos --> redis[(Redis)]
    scheduler[scheduler у lifespan] --> services
    services --> probe[probe<br/>httpx.AsyncClient] --> sites([сайти, що моніторяться])
```

| Шар | Каталог | Відповідальність |
| --- | --- | --- |
| API | `app/api` | HTTP: маршрути, автентифікація, перетворення доменних помилок на статуси |
| Схеми | `app/schemas` | Контракт API, окрема модель на створення, оновлення і читання |
| Сервіси | `app/services` | Сценарії використання, `commit` робить лише сервіс |
| Репозиторії | `app/repositories` | Запити до БД і Redis, лише `flush` |
| Домен | `app/domain` | Оцінка перевірки, uptime, правило інцидентів, помилки |
| Моделі | `app/db` | ORM-моделі, двигун, фабрика сесій |
| Веб | `app/web` | Лендінг, вхід, панель моніторів, сторінка статусу |

### Як працює перевірка

```mermaid
sequenceDiagram
    participant S as Scheduler (кожні 5 с)
    participant DB as PostgreSQL
    participant R as run_probes
    participant T as Сайти
    S->>DB: монітори, у яких минув interval_seconds
    Note over S,DB: сесія закривається до мережевих запитів
    S->>R: CheckTarget[]
    R->>T: паралельно, не більше CHECK_MAX_CONCURRENCY
    Note over R,T: asyncio.timeout на кожну перевірку
    T-->>R: ProbeResult або тип збою
    R-->>S: результати
    S->>DB: Check + last_checked_at + інцидент, SAVEPOINT на монітор
```

Докладніше про ключові рішення: [DECISIONS.md](DECISIONS.md).

## Запуск локально

Потрібні Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 14+ і Redis 6+.

```bash
uv sync
cp .env.example .env

# база для застосунку і окрема для тестів
createuser -P vartovyi          # пароль: vartovyi
createdb -O vartovyi vartovyi
createdb -O vartovyi vartovyi_test

uv run alembic upgrade head
uv run fastapi dev app/main.py
```

- Веб-інтерфейс: http://127.0.0.1:8000 (реєстрація, вхід, панель моніторів)
- Swagger UI: http://127.0.0.1:8000/docs
- Сторінка статусу: http://127.0.0.1:8000/status/{slug}

Інтерфейс написаний на чистих HTML/CSS/JS без фреймворку і build-кроку
(`app/web/static`). Шрифти лежать локально: у Space Grotesk немає кирилиці,
тому під тим самим ім'ям через `unicode-range` кирилицю малює Manrope.

Короткий сценарій через API:

```bash
API=http://127.0.0.1:8000/api/v1
curl -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"email": "me@example.com", "password": "s3cret-passw0rd"}'
TOKEN=$(curl -s -X POST $API/auth/login \
  -d 'username=me@example.com&password=s3cret-passw0rd' | jq -r .access_token)

curl -X PATCH $API/auth/me -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"status_slug": "my-company"}'
curl -X POST $API/monitors -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Сайт", "url": "https://example.com", "is_public": true}'
```

## Налаштування

Усі змінні читаються з оточення або `.env`, див. `.env.example`.

| Змінна | За замовчуванням | Призначення |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://vartovyi:vartovyi@localhost:5432/vartovyi` | PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Чорний список токенів |
| `JWT_SECRET_KEY` | лише для `local` | Обов'язковий поза `ENVIRONMENT=local` |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Час життя access-токена |
| `REFRESH_TOKEN_TTL_SECONDS` | `604800` | Час життя refresh-токена |
| `CHECK_MAX_CONCURRENCY` | `50` | Скільки перевірок одночасно |
| `CHECK_TIMEOUT_SECONDS` | `60` | Глобальна стеля таймауту перевірки |
| `INCIDENT_FAILURE_THRESHOLD` | `2` | Падінь поспіль до відкриття інциденту |
| `SCHEDULER_ENABLED` | `true` | Вмикати лише в одному процесі |
| `LOG_FORMAT` | `json` | `json` або `text` |
| `CORS_ORIGINS` | `[]` | Дозволені origin, порожньо - CORS вимкнено |

## API

| Метод | Шлях | Доступ |
| --- | --- | --- |
| `GET` | `/api/v1/health` | публічний |
| `POST` | `/api/v1/auth/register`, `/login`, `/refresh` | публічний |
| `POST` | `/api/v1/auth/logout` | Bearer |
| `GET`, `PATCH` | `/api/v1/auth/me` | Bearer або `X-API-Key` |
| `GET`, `POST`, `DELETE` | `/api/v1/auth/api-keys` | Bearer або `X-API-Key` |
| `GET`, `POST` | `/api/v1/monitors` | Bearer або `X-API-Key` |
| `GET`, `PATCH`, `DELETE` | `/api/v1/monitors/{id}` | Bearer або `X-API-Key` |
| `GET`, `POST` | `/api/v1/monitors/{id}/checks` | Bearer або `X-API-Key` |
| `GET` | `/api/v1/status/{slug}` | публічний |

Чужий монітор повертає 404, а не 403: відповідь не підтверджує, що такий id існує.

Будь-яка помилка має однаковий вигляд:

```json
{
  "error": {"code": "monitor_not_found", "message": "Монітор не знайдено"}
}
```

Помилки валідації додатково містять `details` зі списком полів.

## Тести і перевірки

```bash
uv run ruff check .
uv run ruff format .
uv run mypy app tests
uv run pytest -v
uv run pytest --cov      # звіт покриття
```

- Домен тестується без БД і мережі
- Репозиторії і API тестуються на справжньому PostgreSQL, схему будують міграції,
  кожен тест працює у транзакції, яка відкочується
- API-тести йдуть через `httpx.AsyncClient` + `ASGITransport` з
  `dependency_overrides`, Redis підміняє fakeredis, зовнішні сайти - respx
- `tests/test_access_control.py` бере всі маршрути з OpenAPI-схеми і перевіряє,
  що кожен захищений відхиляє анонімний і підроблений запит, а новий
  незахищений маршрут ламає тест, доки його свідомо не додадуть до публічних
- Базу для тестів можна змінити через `TEST_DATABASE_URL`, без неї такі тести
  пропускаються

## Deployment

Продакшн-конфігурація: `Dockerfile` (multi-stage) і `docker-compose.prod.yml`
з сервісами `postgres`, `redis`, `migrate` і `app`.

```bash
cp .env.prod.example .env.prod          # задати паролі і JWT_SECRET_KEY
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
curl http://127.0.0.1:8000/api/v1/health
```

- **Образ.** Перша стадія ставить лише runtime-залежності (`uv sync --frozen --no-dev`),
  друга копіює готовий `.venv` у чистий `python:3.12-slim`. pytest, ruff і mypy
  в образ не потрапляють. Працює від некореневого користувача `app`, має
  `HEALTHCHECK` на `/api/v1/health`.
- **Порядок старту.** `postgres` і `redis` мають healthcheck, одноразовий `migrate`
  виконує `alembic upgrade head`, і лише після його успіху стартує `app`.
- **Дані** лежать в іменованих volumes `postgres-data` і `redis-data`. Redis
  працює з AOF, тож відкликані токени переживають перезапуск.
- **Один воркер uvicorn** навмисно: планувальник перевірок має жити в одному
  процесі (див. ADR-003). Масштабувати API горизонтально можна лише після
  винесення планувальника в окремий сервіс.
- **Секрети** в `.env.prod` (у `.gitignore`). Окремий від `.env` файл, бо змінні
  `POSTGRES_*` не є налаштуваннями застосунку, а `Settings` відхиляє невідомі
  ключі з `.env`. Без `JWT_SECRET_KEY` compose не стартує, а зі стандартним
  секретом застосунок відмовиться запускатися в `production`.
- Застосунок очікує реверс-проксі з TLS попереду (uvicorn запущено з
  `--proxy-headers`).

## Що далі

- Ідемпотентність створення моніторів через `Idempotency-Key`
- Експорт історії перевірок у CSV
- Винесення планувальника в окремий процес або Celery beat
