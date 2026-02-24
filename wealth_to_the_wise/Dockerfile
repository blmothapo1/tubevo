# ── Tubevo FastAPI Backend ────────────────────────────────────────────
# Build context is the repo root (Railway/Docker reads from there).
# The app lives in wealth_to_the_wise/.

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System deps (needed by some Python packages + video pipeline) ─────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc libffi-dev libpq-dev \
        ffmpeg \
        fonts-liberation fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*

# ── Python deps (cached layer — only re-runs when requirements change) ─
COPY wealth_to_the_wise/requirements.txt wealth_to_the_wise/requirements-backend.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r requirements-backend.txt

# ── Application code ─────────────────────────────────────────────────
COPY wealth_to_the_wise/ .

# Ensure output dir exists (config.py writes logs here)
RUN mkdir -p output

# ── Runtime ──────────────────────────────────────────────────────────
EXPOSE 8000

# Railway sets $PORT dynamically; fall back to 8000 for local Docker
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}
