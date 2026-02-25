# Multi-stage build
FROM python:3.9-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt
RUN pip install --user --no-cache-dir cedarpy redis

# Runtime stage
FROM python:3.9-slim

WORKDIR /app

# OCI metadata labels
LABEL org.opencontainers.image.title="Intent Analyzer Gateway" \
      org.opencontainers.image.description="AI safety guardrail for LLM applications" \
      org.opencontainers.image.source="https://github.com/Vero-labs/IntentAnalyser-AIGuardrail" \
      org.opencontainers.image.licenses="MIT"

# Install curl for health checks, create non-root user
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app && adduser --system --group app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH
ENV HOME=/home/app
ENV PYTHONPATH=/home/app/.local/lib/python3.9/site-packages

# Copy application code
COPY app /app/app

# Ownership
RUN chown -R app:app /app && chown -R app:app /home/app

USER app

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Health check — orchestrators (Docker, ECS, K8s liveness probes) use this
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
