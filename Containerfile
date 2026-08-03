# Local development + reviewer reproducibility only (ARCHITECTURE.md §12.3).
# Vercel does not build or run this file - it deploys the same ASGI app as
# serverless functions directly from source (see api/index.py, vercel.json).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg[binary] wheels and healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY smartreco_agent ./smartreco_agent
RUN pip install --no-cache-dir .

COPY migrations ./migrations
COPY scripts ./scripts

RUN useradd --create-home --uid 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "smartreco_agent.src.api:app", "--host", "0.0.0.0", "--port", "8000"]
