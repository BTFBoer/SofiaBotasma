FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATABASE_PATH=/app/data/sofia.db \
    PERSONA_DIR=/app/persona

WORKDIR /app

RUN useradd --create-home --uid 10001 sofia

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
# Base persona files only; *.private.yaml is excluded by .dockerignore and mounted at runtime.
COPY persona ./persona

RUN mkdir -p /app/data && chown -R sofia:sofia /app
USER sofia

VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
    CMD ["python", "-m", "app.healthcheck"]

CMD ["python", "-m", "app"]
