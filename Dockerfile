FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app ./app
COPY main.py . 
# (Note: main.py is likely redundant if we run app.main, but keeping structure clean)

# Environment
ENV INTENT_ANALYZER_MODEL=bart
ENV PORT=8002

EXPOSE 8002

# Use gunicorn as process manager for production (uvicorn workers)
# Or just uvicorn directly if desired. Render recommends gunicorn.
# For now, sticking to uvicorn per user request but correct path.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
