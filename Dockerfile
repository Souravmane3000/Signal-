# Signal production image — FastAPI + APScheduler (Northflank)
# Entrypoint unchanged: uvicorn api.main:app

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# System deps for psycopg binary wheels / SSL
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY agent ./agent
COPY api ./api
COPY scripts ./scripts

# Default Northflank / BUILD_SPEC port; override with PORT env var
EXPOSE 8080

# Shell form so ${PORT} expands at runtime
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
