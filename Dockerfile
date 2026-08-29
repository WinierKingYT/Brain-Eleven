# Brain-Eleven v3 Production Image
FROM python:3.13-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY requirements.txt .
COPY scripts/ ./scripts/
COPY .claude/ ./.claude/
COPY tests/ ./tests/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN addgroup --system app && adduser --system --group app
RUN chown -R app:app /app

USER app

# Environment
ENV PYTHONUNBUFFERED=1
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV VAULT_PATH=/vault
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV POSTGRES_HOST=postgres
ENV POSTGRES_USER=brain
ENV POSTGRES_DB=brain_eleven

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Default: Run API server
CMD ["python", "scripts/search-api.py"]
