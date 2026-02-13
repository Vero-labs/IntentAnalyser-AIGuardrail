"""
Tri-Axis Intent Analyzer — API Routes.

Pipeline:
  1. Risk Detector (Layer A) — runs FIRST, short-circuits on critical signals
  2. Action Detector + Domain Classifier — run in PARALLEL (independent axes)
  3. Evaluation Engine — deterministic rules logged for observability

Output is flat: action, domain, risk_signals, confidence, ambiguity.
Trace available via ?debug=true.
"""

from fastapi import APIRouter, HTTPException, Query
from app.schemas.intent import (
    IntentRequest, IntentResponse, IntentResponseDebug, DetectorTrace,
)
from app.services.classifiers.risk_detector import RiskDetector
from app.services.classifiers.action_detector import ActionDetector
from app.services.classifiers.domain_classifier import DomainClassifier
from app.services.evaluation_engine import evaluate, AMBIGUITY_LOW, AMBIGUITY_HIGH
from app.core.axes import RiskSignal
import time
import asyncio
import hashlib
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

classifiers = {}

@router.on_event("startup")
async def startup_event():
    logger.info("Initializing Tri-Axis Classifiers...")
    classifiers["risk"]   = RiskDetector()
    classifiers["action"] = ActionDetector()
    classifiers["domain"] = DomainClassifier()
    await classifiers["risk"].load()
    await classifiers["action"].load()
    await classifiers["domain"].load()
    logger.info("All Tri-Axis Classifiers Initialized.")


CACHE = {}
MAX_CACHE_SIZE = 500


@router.post("/intent")
async def analyze_intent(request: IntentRequest, debug: bool = Query(False)):
    start_time = time.time()

    # Input normalization
    input_text = request.text
    if not input_text and request.messages:
        input_text = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    if not input_text:
        raise HTTPException(status_code=400, detail="Text or messages required")

    # Cache lookup
    text_hash = hashlib.md5(input_text.encode()).hexdigest()
    if text_hash in CACHE:
        cached = CACHE[text_hash]
        cached["processing_time_ms"] = round((time.time() - start_time) * 1000, 2)
        return cached

    # ── Layer A: Risk Detector (first, always) ────────────────────────────
    risk_result = classifiers["risk"].classify(input_text)
    risk_signals = risk_result["signals"]
    risk_score = risk_result["risk_score"]

    # ── Layer B + C: Action + Domain (parallel, independent) ──────────────
    action_result, domain_result = await asyncio.gather(
        asyncio.to_thread(classifiers["action"].classify, input_text),
        asyncio.to_thread(classifiers["domain"].classify, input_text),
    )

    action = action_result["result"]
    action_confidence = round(action_result["confidence"], 2)
    domain = domain_result["result"]
    domain_confidence = round(domain_result["confidence"], 2)

    # ── Ambiguity detection ───────────────────────────────────────────────
    min_conf = min(action_confidence, domain_confidence)
    ambiguity = AMBIGUITY_LOW <= min_conf < AMBIGUITY_HIGH

    # ── Evaluation (logged, not in response) ──────────────────────────────
    role = "general"
    eval_result = evaluate(
        action=action,
        action_confidence=action_confidence,
        domain=domain,
        domain_confidence=domain_confidence,
        risk_signals=risk_signals,
        risk_score=risk_score,
        role=role,
    )

    logger.info(
        f"RESULT: action={action.value}({action_confidence:.2f}) "
        f"domain={domain.value}({domain_confidence:.2f}) "
        f"risk={risk_score:.2f} signals=[{','.join(s.value for s in risk_signals)}] "
        f"decision={eval_result.decision} reason={eval_result.reason}"
    )

    elapsed = round((time.time() - start_time) * 1000, 2)

    # ── Build flat response ───────────────────────────────────────────────
    response_data = {
        "action": action.value,
        "action_confidence": action_confidence,
        "domain": domain.value,
        "domain_confidence": domain_confidence,
        "risk_signals": [s.value for s in risk_signals],
        "risk_score": round(risk_score, 2),
        "ambiguity": ambiguity,
        "processing_time_ms": elapsed,
    }

    # Debug trace (only if requested)
    if debug:
        response_data["trace"] = {
            "regex_triggered": risk_result["regex_triggered"],
            "regex_signals": risk_result["regex_signals"],
            "risk_semantic_scores": risk_result["semantic_scores"],
            "risk_detection_path": risk_result["detection_path"],
            "action_all_scores": action_result["all_scores"],
            "domain_all_scores": domain_result["all_scores"],
            "dominant_layer": "risk" if risk_result["regex_triggered"] else (
                "action" if action_confidence > domain_confidence else "domain"
            ),
            "pipeline_short_circuited": risk_result["regex_triggered"] and risk_score >= 1.0,
        }

    # Cache
    if len(CACHE) < MAX_CACHE_SIZE:
        CACHE[text_hash] = response_data

    return response_data


@router.get("/health")
def health():
    return {
        "status": "ok",
        "architecture": "tri-axis",
        "classifiers": list(classifiers.keys()),
    }
