FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only.
# weasyprint needs libpango / libharfbuzz / libpangoft2 to render
# fonts + text shaping at PDF-generation time. Without them the
# renderer falls back to returning raw HTML as bytes, which Gmail
# then fails to preview as a PDF (2026-04-24 incident).
RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/ .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Use startup.sh so alembic migrations run before uvicorn boots
# (see commit history for the auto-migrate change).
CMD ["bash", "startup.sh"]
