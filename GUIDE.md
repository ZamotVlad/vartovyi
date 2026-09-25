# Як влаштований Vartovyi: путівник по коду

Документ для читання коду з нуля. Порядок розділів - той, у якому варто
відкривати файли. Короткі архітектурні рішення з аргументами лежать у
[DECISIONS.md](DECISIONS.md), запуск - у [README.md](README.md).

## 1. Точка входу: `app/main.py`

`create_app()` збирає застосунок: підключає роутери, обробники помилок,
middleware і статику. Фабрика (а не глобальний `app = FastAPI()`) потрібна
тестам: кожен тест може створити свіжий застосунок з потрібними налаштуваннями.

`lifespan` - асинхронний контекстний менеджер. Код до `yield` виконується один
раз при старті, після - при зупинці. Тут створюються ресурси, які живуть увесь
час роботи процесу:

- пул з'єднань з БД (`create_engine`) і фабрика сесій;
- клієнт Redis;
- один `httpx.AsyncClient` для перевірок сайтів;
- фонова задача планувальника (`asyncio.create_task`).

Усе кладеться в `app.state`, а залежності (`app/api/deps.py`) дістають це звідти.

## 2. Налаштування: `app/config.py`

`Settings` на pydantic-settings читає змінні оточення і `.env`, валідує типи
та межі (`Field(ge=..., le=...)`). `extra="forbid"` ловить одруківки в `.env`.
`model_validator` не дає запустити продакшн зі стандартним JWT-секретом.
`get_settings()` обгорнутий в `lru_cache`, тож налаштування читаються один раз.

## 3. Шари і напрямок залежностей

```
api/endpoints  ->  services  ->  repositories  ->  db/models
      |               |
      v               v
   schemas          domain
```

Правило: шар імпортує тільки нижчі. Навіщо: бізнес-логіку можна тестувати і
перевикористовувати без HTTP, а заміна БД чи фреймворку зачіпає один шар.

### 3.1 `app/domain` - чиста логіка

Жодного FastAPI чи SQLAlchemy, лише dataclass і функції. Тому тести домену
не потребують БД і виконуються за мілісекунди.

- `check.py` - `evaluate(probe, expectation)`: з «сирого факту» (код, час,
  тіло, збій) робить вердикт UP / DEGRADED / DOWN з причиною.
- `uptime.py` - підрахунок відсотка доступності.
- `incident.py` - `decide_incident_action`: відкрити інцидент після N падінь
  поспіль, закрити після першого успіху.
- `monitor.py` - правила узгодженості таймаутів (одне джерело для створення і PATCH).
- `errors.py` - доменні помилки за категоріями. Про HTTP-статуси вони нічого не знають.

### 3.2 `app/schemas` - контракт API (Pydantic v2)

На кожну сутність окремі моделі: `MonitorCreate` (що можна надіслати),
`MonitorUpdate` (усе необов'язкове для PATCH), `MonitorRead` (що повертаємо).
Так поле `owner_id` чи `hashed_password` не може випадково потрапити у відповідь.
`ConfigDict(from_attributes=True)` дозволяє будувати схему прямо з ORM-об'єкта.
`model_dump(exclude_unset=True)` у PATCH відрізняє «поле не надіслали» від
«надіслали null».

### 3.3 `app/db` - моделі SQLAlchemy 2.0

`Base(DeclarativeBase)` з конвенцією імен обмежень (потрібна Alembic).
Колонки описуються як `name: Mapped[str] = mapped_column(String(100))` - тип
Python і тип колонки в одному місці, mypy їх розуміє.

Важливі async-нюанси:
- `expire_on_commit=False` - після commit атрибути лишаються доступними;
  інакше звернення до них викликало б прихований запит, а в async це помилка
  `MissingGreenlet`.
- `eager_defaults=True` - значення, які ставить БД (`created_at`), повертаються
  одразу через `RETURNING`.
- Зв'язки не вантажаться ліниво: де потрібно, явно `joinedload`.

### 3.4 `app/repositories` - доступ до даних

Класи з методами-запитами (`get_for_owner`, `list_page`, `latest_for_monitors`).
Правило: репозиторій робить `flush`, але ніколи `commit`. Межу транзакції
визначає сервіс, бо лише він знає, де закінчується «одна бізнес-операція».

Цікаві запити:
- `MonitorRepository.list_page` - фільтри, екранування `%` у LIKE, стабільне
  сортування, `count()` з тими ж фільтрами для пагінації.
- `CheckRepository.status_counts_since` - `GROUP BY` у БД замість завантаження
  тисяч рядків у Python.
- `CheckRepository.latest_for_monitors` - `DISTINCT ON`: остання перевірка для
  кожного монітора одним запитом.
- `TokenBlacklist` - репозиторій над Redis.

### 3.5 `app/services` - сценарії

Сервіс отримує сесію в конструкторі, створює потрібні репозиторії, викликає
доменні правила і робить `commit`. Приклад `MonitorService.update`: знаходить
монітор лише серед своїх (`get_for_owner`), об'єднує PATCH зі збереженим
станом, перевіряє доменне правило, зберігає.

### 3.6 `app/api` - HTTP

- `v1/endpoints/*.py` - маршрути. Тонкі: прийняти схему, викликати сервіс,
  повернути результат. Без try/except.
- `deps.py` - залежності (`Depends`). Ланцюжок:
  `get_session` -> `get_auth_service` -> `get_current_user` -> `get_current_active_user`.
  FastAPI сам будує цей граф і кешує залежність у межах запиту.
  `Annotated[User, Depends(...)]` винесено в псевдоніми (`CurrentUserDep`), щоб
  сигнатури ендпоінтів були короткими.
- `errors.py` - обробники винятків. Доменна помилка перетворюється на статус за
  категорією (`NotFoundError` -> 404), тіло завжди `{"error": {...}}`.
- `middleware.py` - чистий ASGI middleware (див. розділ 6).

## 4. Життя одного запиту: `GET /api/v1/monitors/{id}`

1. `RequestContextMiddleware` створює request id, кладе його в `contextvars`,
   запускає таймер.
2. Маршрутизатор знаходить ендпоінт `get_monitor`.
3. FastAPI вирішує залежності: відкриває сесію (`get_session` з `yield`),
   перевіряє токен (`get_current_user`), перевіряє, що користувач активний.
4. Ендпоінт викликає `MonitorService.get(user, id)`.
5. Репозиторій робить `SELECT ... WHERE id = :id AND owner_id = :owner`. Чужий
   монітор просто не знаходиться, тому відповідь 404, а не 403: так не можна
   дізнатися, що чужий id існує.
6. Якщо не знайдено - `MonitorNotFoundError`, обробник перетворює на 404.
7. Інакше ORM-об'єкт серіалізується через `response_model=MonitorRead`.
8. Код після `yield` у `get_session` закриває сесію. Middleware додає заголовки
   `X-Request-ID` і `X-Process-Time-Ms` та пише access-лог.

## 5. Автентифікація (`core/security.py`, `services/auth.py`)

- Пароль хешується bcrypt через passlib. Довжина обмежена 72 байтами, бо bcrypt
  відкидає решту.
- Вхід повертає пару токенів. Access живе 15 хв, refresh 7 днів. У кожного
  свій `jti` (унікальний id) і `type`.
- Кожен запит з access перевіряє `jti` у Redis: так токен можна відкликати до
  закінчення терміну.
- `/refresh` робить ротацію: старий refresh атомарно (`SET NX`) потрапляє до
  чорного списку, два паралельні refresh не отримають дві пари.
- API-ключ: випадковий рядок, у БД лише SHA-256. Передається заголовком `X-API-Key`.
- `get_current_user` приймає або Bearer, або API-ключ.

## 6. Middleware і логування

`RequestContextMiddleware` написаний як чистий ASGI-клас (`__call__(scope,
receive, send)`), а не через `BaseHTTPMiddleware`: той запускає ендпоінт в
окремій задачі, і `contextvars` перестають працювати. Middleware:

- обгортає `send`, щоб додати заголовки у момент старту відповіді;
- ловить будь-який непійманий виняток і віддає 500 без подробиць (JSON для API,
  HTML-сторінку для браузера);
- пише структурований лог. `JsonFormatter` у `core/logging.py` додає до кожного
  запису `request_id`, тож усі логи одного запиту легко знайти.

## 7. Рушій перевірок (`services/probe.py`, `check_runner.py`, `check.py`, `scheduler.py`)

1. `run_scheduler` - нескінченний цикл: кожні N секунд викликає `run_due_checks`.
2. `run_due_checks` відкриває сесію, бере монітори з простроченим інтервалом
   (`list_due`) і **закриває сесію** до мережевих запитів, щоб повільні сайти
   не тримали з'єднання з пулу.
3. `run_probes` запускає перевірки в `asyncio.TaskGroup`. `Semaphore` обмежує
   паралелізм, наприклад до 50 одночасних.
4. `probe` робить GET у `asyncio.timeout()`. Мережевий збій повертається як
   результат з причиною, а не як виняток.
5. Нова сесія зберігає результати. Для кожного монітора `SAVEPOINT`
   (`begin_nested`), тож помилка одного не відкотить інші. `CheckService.record`
   оцінює результат доменом і оновлює інцидент.

Приклади async-концепцій у коді: `TaskGroup` (структурована конкурентність:
вихід із блоку лише коли всі задачі завершились), `Semaphore`,
`asyncio.timeout`, `create_task` + `cancel` у lifespan.

## 8. Міграції (`migrations/`)

Alembic порівнює `Base.metadata` з реальною БД і генерує міграцію
(`alembic revision --autogenerate -m "..."`). `env.py` бере URL з налаштувань
застосунку. Тест `test_models_match_migrations` падає, якщо модель змінили, а
міграцію не створили.

## 9. Фронтенд (`app/web`)

- `routes.py` віддає HTML-файли (`FileResponse`), `robots.txt` і `sitemap.xml`.
  Статика змонтована на `/static`.
- `static/js/api.js` - спільний клієнт: додає Bearer-токен, при 401 один раз
  пробує `/auth/refresh`, інакше веде на `/login`. Помилки перетворює на
  зрозумілі тексти.
- `dashboard.js` рендерить рядки через `createElement` і `textContent` (ніколи
  `innerHTML`: назви задає користувач, це захист від XSS).
- `css/app.css` - токени кольорів у `:root`, лампа-індикатор, анімації з
  `@property`, повага до `prefers-reduced-motion`.

## 10. Тести (`tests/`)

- `conftest.py` - ключове місце:
  - `db_engine` піднімає схему **міграціями** на тестовій БД;
  - `db_connection` відкриває транзакцію, яку після тесту відкочують;
    `join_transaction_mode="create_savepoint"` робить `commit` у коді savepoint-ом,
    тож тести ізольовані і швидкі;
  - `client` - `httpx.AsyncClient` з `ASGITransport` (без справжнього сервера) і
    `dependency_overrides`, які підміняють сесію, Redis (fakeredis) і HTTP-клієнт.
- respx перехоплює запити httpx: сайти, що моніторяться, імітуються без мережі.
- `test_access_control.py` бере всі маршрути з OpenAPI і перевіряє, що кожен
  захищений відхиляє анонімний і підроблений запит.

## Що почитати в коді першим

1. `app/main.py` - як усе збирається.
2. `app/api/v1/endpoints/monitors.py` -> `services/monitor.py` ->
   `repositories/monitor.py` - один повний вертикальний зріз.
3. `app/api/deps.py` - dependency injection у FastAPI.
4. `tests/conftest.py` і `tests/test_api_monitors.py` - як це тестується.
5. `app/services/check_runner.py` і `probe.py` - async на практиці.
