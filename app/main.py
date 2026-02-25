import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.env import load_env_file
from app.core.logging import setup_logging
from app.services.runtime_config import CONFIG_PATH, RuntimeConfigError, load_runtime_config

# Load local development env vars before app startup.
load_env_file(os.getenv("GUARDRAIL_ENV_FILE", ".env"))

from app.api.routes import router as api_router  # noqa: E402

setup_logging(level="INFO")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Intent Analyzer Guardrail",
    description="Production-grade Intent Analysis with Multi-Layer Detection",
    version="4.0.1"
)

# 1. Trusted Host Middleware (prevent Host header attacks)
# Configure via TRUSTED_HOSTS env var (comma-separated), e.g. "localhost,myapp.render.com"
_default_trusted = "localhost,127.0.0.1"
_trusted_hosts = [h.strip() for h in os.getenv("TRUSTED_HOSTS", _default_trusted).split(",") if h.strip()]
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_trusted_hosts,
)

# 2. CORS Middleware (Restrict cross-origin requests)
# Configure via CORS_ORIGINS env var (comma-separated), or set to "*" to allow all
_default_origins = "http://localhost,http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000"
_cors_origins_raw = os.getenv("CORS_ORIGINS", _default_origins)
_cors_origins = ["*"] if _cors_origins_raw.strip() == "*" else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
