from fastapi import APIRouter, HTTPException, Depends
from app.schemas.intent import IntentRequest, IntentResponse
from app.services.detectors.regex import RegexDetector
from app.services.detectors.semantic import SemanticDetector
from app.services.detectors.zeroshot import ZeroShotDetector
from app.services.risk_engine import RiskEngine
import time
import logging
import hashlib

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

# Simple in-memory cache
CACHE = {}

@router.post("/intent", response_model=IntentResponse)
async def analyze_intent(request: IntentRequest):
    start_time = time.time()
    
    # 1. Input Normalization
    input_text = request.text
    if not input_text and request.messages:
        input_text = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    
    if not input_text:
        raise HTTPException(status_code=400, detail="Text or messages required")

    # 2. Cache Lookup
    text_hash = hashlib.md5(input_text.encode()).hexdigest()
    if text_hash in CACHE:
        cached_res = CACHE[text_hash]
        cached_res.processing_time_ms = (time.time() - start_time) * 1000
        logger.info(f"Cache Hit: {text_hash}")
        return cached_res

    # 3. Detection Pipeline
    import asyncio
    regex_res = detectors["regex"].detect(input_text)
    
    # OPTIMIZATION 1: Regex Short-circuit
    if regex_res["detected"]:
        response = risk_engine.calculate_risk(regex_res, {}, {})
        response.processing_time_ms = (time.time() - start_time) * 1000
        logger.info(f"Short-circuit: Regex ({regex_res['intent']})")
        return response

    # OPTIMIZATION 2: Semantic Short-circuit (Faster than Zero-shot)
    semantic_res = await asyncio.to_thread(detectors["semantic"].detect, input_text)
    
    # If semantic match is very high confidence, skip the heavy Zero-shot model
    if semantic_res["detected"] and semantic_res["score"] > 0.94:
        zeroshot_res = {"detected": False, "score": 0.0, "intent": None, "metadata": {"status": "skipped_high_confidence"}}
        logger.info(f"Short-circuit: Semantic ({semantic_res['score']:.2f})")
    else:
        # Zero-shot is the bottleneck (BART model)
        zeroshot_res = await asyncio.to_thread(detectors["zeroshot"].detect, input_text)

    # 4. Final Aggregation
    response = risk_engine.calculate_risk(regex_res, semantic_res, zeroshot_res)
    response.processing_time_ms = (time.time() - start_time) * 1000
    
    # Store in cache (cap at 500 entries)
    if len(CACHE) < 500:
        CACHE[text_hash] = response
    
    return response

@router.get("/health")
def health():
    return {"status": "ok", "detectors": list(detectors.keys())}
