FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source code and eval harness
COPY src/ /app/src/
COPY eval/ /app/eval/

EXPOSE 8000

ENV OMNIGATE_HOST=0.0.0.0
ENV OMNIGATE_PORT=8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
