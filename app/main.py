from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.core.env import load_env_file
from app.core.logging import setup_logging
from app.services.runtime_config import CONFIG_PATH, RuntimeConfigError, load_runtime_config
import logging
import os

# Load local development env vars before app startup.
load_env_file(os.getenv("GUARDRAIL_ENV_FILE", ".env"))

from app.api.routes import router as api_router

setup_logging(level="INFO")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Intent Analyzer Guardrail",
    description="Production-grade Intent Analysis with Multi-Layer Detection",
    version="4.0.0"
)

# 1. Trusted Host Middleware (prevent Host header attacks)
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["localhost", "127.0.0.1", "*.example.com"] # Update for production
)

# 2. CORS Middleware (Restrict cross-origin requests)
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 3. Custom Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    config_host = "0.0.0.0"
    config_port = 8000
    try:
        runtime_config = load_runtime_config(CONFIG_PATH)
        config_host = runtime_config.server_host
        config_port = runtime_config.server_port
    except RuntimeConfigError:
        pass

    host = os.getenv("HOST", config_host)
    port = int(os.getenv("PORT", str(config_port)))
    uvicorn.run(app, host=host, port=port)
