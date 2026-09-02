# Brain-Eleven v3 Production Image
FROM python:3.13-slim

WORKDIR /app

# Refresh the runtime OS packages while building.  The Python dependencies
# currently resolve to wheels, so a compiler does not need to be shipped in
# the production image.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY requirements.txt .
COPY scripts/ ./scripts/
COPY .claude/ ./.claude/
COPY tests/ ./tests/

# Install Python dependencies. The base image ships vulnerable distribution
# records for build tooling and msgpack. Remove those records before installing
# patched versions so the final image filesystem contains only the patched
# distributions (and so image scanners can verify that fact).
RUN python -m pip uninstall --yes setuptools msgpack \
    && python -m pip install --no-cache-dir \
        "setuptools>=78.1.1" \
        "msgpack>=1.2.1" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check

# Create non-root user
RUN addgroup --system app && adduser --system --group app
RUN chown -R app:app /app

USER app

# Environment
ENV PYTHONUNBUFFERED=1
ENV VAULT_PATH=/vault
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV POSTGRES_HOST=postgres
ENV POSTGRES_USER=brain
ENV POSTGRES_DB=brain_eleven

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health', timeout=5).read()" || exit 1

# Default: Run API server
CMD ["python", "scripts/search-api.py"]
