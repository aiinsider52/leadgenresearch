# Full-functionality container: FastAPI + Playwright/Chromium for Google Maps.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Python deps first (better layer caching). Playwright is Docker-only (Vercel stays slim).
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt "playwright>=1.40"

# Chromium + its OS dependencies for the live Google Maps worker.
RUN python -m playwright install --with-deps chromium

COPY . .

# Render/Railway inject $PORT; default 8000 locally.
CMD ["sh", "-c", "uvicorn leadgen.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
