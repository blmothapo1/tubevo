# ── Tubevo FastAPI Backend ────────────────────────────────────────────
# Build:  docker build -t tubevo-backend .
# Run:    docker run -p 8000:8000 --env-file .env tubevo-backend

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── System deps (needed by some Python packages) ─────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# ── Python deps (cached layer — only re-runs when requirements change) ─
COPY requirements.txt requirements-backend.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r requirements-backend.txt

# ── Application code ─────────────────────────────────────────────────
COPY . .

# ── Runtime ──────────────────────────────────────────────────────────
EXPOSE 8000

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
