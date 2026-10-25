# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install .

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATABASE_URL=sqlite+pysqlite:////data/app.sqlite \
    APP_ENV=development \
    HOST=0.0.0.0 \
    PORT=8000 \
    HOME=/tmp

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /nonexistent --shell /usr/sbin/nologin appuser \
    && mkdir -p /data /app \
    && chown -R appuser:appuser /data /app

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod 0755 /app/entrypoint.sh \
    && chown -R appuser:appuser /app

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"
ENTRYPOINT ["/app/entrypoint.sh"]
