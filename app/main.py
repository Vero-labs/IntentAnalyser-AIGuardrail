from fastapi import FastAPI
from app.api.routes import router as api_router
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Intent Analyzer Guardrail",
    description="Production-grade Intent Analysis with Multi-Layer Detection",
    version="3.0.0"
)

app.include_router(api_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
