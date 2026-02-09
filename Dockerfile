# Document Scraper (Bloomberg & CMECF) - Railway / Docker
# Uses Playwright + Chromium for browser automation (must run headless in production)

FROM python:3.11-slim

# Install system deps required by Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend and frontend (paths expected by main.py)
COPY backend/ ./backend/
COPY frontend/ ./frontend/

WORKDIR /app/backend

# Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Playwright: install Chromium only (headless)
RUN playwright install chromium && playwright install-deps chromium

# Create dirs for downloads/logs (ephemeral unless you mount a volume)
RUN mkdir -p /app/downloads/BLOOMBERG /app/downloads/PACER /app/logs /app/screenshots

# Railway / Cloud: bind to 0.0.0.0 and use PORT from env
ENV APP_HOST=0.0.0.0
# Downloads under /app so they exist; override with volume path if needed
ENV DOWNLOADS_BASE_DIR=/app/downloads
ENV BLOOMBERG_DOWNLOADS_DIR=/app/downloads/BLOOMBERG
ENV PACER_DOWNLOADS_DIR=/app/downloads/PACER
ENV LOGS_DIR=/app/logs
ENV SCREENSHOTS_DIR=/app/screenshots
# Headless required when no display
ENV HEADLESS_MODE=true

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
