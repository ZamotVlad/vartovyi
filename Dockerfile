# syntax=docker/dockerfile:1

# ---------- збірка залежностей ----------
FROM python:3.12-slim AS builder

# Версія uv зафіксована, як і uv.lock: збірка відтворювана
RUN pip install --no-cache-dir uv==0.8.17

# Байткод компілюємо на збірці, щоб контейнер не робив цього при кожному старті;
# copy-режим, бо кеш uv і .venv на різних файлових системах
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Спершу лише маніфести: шар із залежностями кешується, поки не змінився uv.lock
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ---------- рантайм ----------
FROM python:3.12-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# У slim-образі немає curl, тож перевірка на стандартній бібліотеці
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"]

# Один воркер навмисно: планувальник перевірок має жити рівно в одному процесі (ADR-003)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
