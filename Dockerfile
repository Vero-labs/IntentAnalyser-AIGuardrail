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

# Create non-root user
RUN addgroup --system app && adduser --system --group app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH
ENV HOME=/home/app
ENV PYTHONPATH=/home/app/.local/lib/python3.9/site-packages

# Copy application code
COPY app /app/app
# policies is inside app locally: app/policies
# But we need it in python path or relative.
# Simpler: Copy everything as is.

# If local structure is:
# /app
#   /policies
#     main.cedar

# Dockerfile is at root.
# So COPY app /app/app copies everything in app folder to /app/app in container.
# If policies is in app/policies, it's already copied!
# Let's double check file structure.

# Ownership
RUN chown -R app:app /app && chown -R app:app /home/app

USER app

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
