from fastapi import APIRouter, HTTPException, Depends
from app.schemas.intent import IntentRequest, IntentResponse
from app.services.detectors.regex import RegexDetector
from app.services.detectors.semantic import SemanticDetector
from app.services.detectors.zeroshot import ZeroShotDetector
from app.services.risk_engine import RiskEngine
import time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Global instances (naive singleton for now)
detectors = {}
risk_engine = RiskEngine()

async def get_detectors():
    return detectors

@router.on_event("startup")
async def startup_event():
    logger.info("Initializing Detectors...")
    detectors["regex"] = RegexDetector()
    detectors["semantic"] = SemanticDetector()
    detectors["zeroshot"] = ZeroShotDetector()
    
    await detectors["regex"].load()
    await detectors["semantic"].load()
    await detectors["zeroshot"].load()
    logger.info("Detectors Initialized.")

@router.post("/intent", response_model=IntentResponse)
async def analyze_intent(request: IntentRequest):
    start_time = time.time()
    
    # 1. Input Normalization
    input_text = request.text
    if not input_text and request.messages:
        input_text = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    
    if not input_text:
        raise HTTPException(status_code=400, detail="Text or messages required")

    # 2. Parallel Detection
    import asyncio
    
    # regex is fast enough to run sync, but semantic and zeroshot block
    regex_res = detectors["regex"].detect(input_text)
    
    # Prepare parallel tasks
    async def run_semantic():
        return await asyncio.to_thread(detectors["semantic"].detect, input_text)
        
    async def run_zeroshot():
        return await asyncio.to_thread(detectors["zeroshot"].detect, input_text)

    # Execute in parallel
    semantic_res, zeroshot_res = await asyncio.gather(
        run_semantic(),
        run_zeroshot()
    )

    # 3. Risk Aggregation
    response = risk_engine.calculate_risk(regex_res, semantic_res, zeroshot_res)
    
    # 4. Telemetry (Processing Time)
    response.processing_time_ms = (time.time() - start_time) * 1000
    
    return response

@router.get("/health")
def health():
    return {"status": "ok", "detectors": list(detectors.keys())}
