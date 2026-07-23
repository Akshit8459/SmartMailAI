# Production Multi-Stage Dockerfile for SmartMail AI Backend
FROM python:3.12-slim as builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r /app/requirements.txt

# Final Runtime Image
FROM python:3.12-slim

WORKDIR /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application backend & frontend
COPY backend /app/backend
COPY frontend /app/frontend
# Copy environment template
COPY .env.example /app/.env.example

# Create storage directory for attachments
RUN mkdir -p /app/storage/attachments

EXPOSE 8000

ENV PYTHONPATH=/app/backend
CMD ["python", "backend/main.py"]
