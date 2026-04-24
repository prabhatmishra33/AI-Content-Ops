# ──── Stage 1: Dependencies ────
FROM python:3.12-slim AS deps
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ──── Stage 2: Runtime ────
FROM python:3.12-slim
WORKDIR /app

# ffmpeg for thumbnail generation
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/requirements.txt .

# Create storage dirs
RUN mkdir -p storage/uploads storage/audio_news storage/media_mixed

# Non-root user
RUN useradd -r -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
