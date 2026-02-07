FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml uv.lock README.md /app/
COPY alembic.ini /app/alembic.ini
COPY src /app/src
COPY alembic /app/alembic
COPY config /app/config

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
