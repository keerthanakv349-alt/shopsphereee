# --- Build stage: install deps into a venv so the final image has no build tools ---
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

# --- Runtime stage: slim image, no compilers, no source-of-truth for secrets baked in ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"
COPY . .

EXPOSE 8000
# Gunicorn manages multiple Uvicorn worker processes — Uvicorn alone is
# single-process, which wastes multi-core servers in production.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4"]
