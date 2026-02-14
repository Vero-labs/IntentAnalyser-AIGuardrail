"""
Tri-Axis Intent Analyzer — API Routes.

Pipeline:
  1. Risk Detector (Layer A) — runs FIRST, short-circuits on critical signals
  2. Action Detector + Domain Classifier — run in PARALLEL (independent axes)
  3. Evaluation Engine — deterministic rules logged for observability

Output is flat: action, domain, risk_signals, confidence, ambiguity.
Trace available via ?debug=true.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from app.schemas.intent import (
    IntentRequest, IntentResponse, IntentResponseDebug,
)
from app.services.detectors.zeroshot import ZeroShotDetector
from app.core.cache import CacheService
from app.core.rate_limit import RateLimiter
from app.services.risk_engine import RiskEngine
from app.services.priority_engine import PriorityEngine
from app.services.detectors.regex import RegexDetector
from app.services.detectors.semantic import SemanticDetector
from app.services.policy_engine import PolicyEngine
from app.core.taxonomy import IntentCategory, IntentTier, TIER_MAPPING
import asyncio
import hashlib
import logging
import time

router = APIRouter()
logger = logging.getLogger(__name__)

classifiers = {}
cache_service = CacheService()
rate_limiter = RateLimiter(requests_per_minute=6000)

@router.on_event("startup")
async def startup_event():
    logger.info("Initializing Classifiers...")
    classifiers["regex"] = RegexDetector()
    classifiers["semantic"] = SemanticDetector()
    classifiers["zeroshot"] = ZeroShotDetector()
    
    await classifiers["regex"].load()
    await classifiers["semantic"].load()
    await classifiers["zeroshot"].load()
    logger.info("Classifiers Initialized.")

# Engines
risk_engine = RiskEngine()
priority_engine = PriorityEngine()
policy_engine = PolicyEngine()


def _map_intent_to_domain(intent: IntentCategory) -> str:
    """Helper to map intent category to policy domain."""
    val = intent.value
    if val.startswith("code.") or val.startswith("sys.") or val.startswith("tool."):
        return "technical"
    if val.startswith("security."):
        return "security"
    if val == "policy.financial_advice":
        return "finance"
    if val.startswith("info.") or val.startswith("conv."):
        return "general_knowledge"
    return "unknown"

@router.post("/intent", dependencies=[Depends(rate_limiter)])
async def analyze_intent(request: IntentRequest, debug: bool = Query(False)):
    start_time = time.time()

    # Input normalization
    input_text = request.text
    if not input_text and request.messages:
        input_text = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    if not input_text:
        raise HTTPException(status_code=400, detail="Text or messages required")

    # Cache lookup
    cached = cache_service.get(input_text)
    if cached:
        cached["processing_time_ms"] = round((time.time() - start_time) * 1000, 2)
        return cached

    # 1. Run Detectors in Parallel
    regex_result = classifiers["regex"].detect(input_text)
    semantic_result = classifiers["semantic"].detect(input_text)
    zeroshot_result = classifiers["zeroshot"].detect(input_text)
    
    # Placeholder for Keyword
    keyword_result = {"detected": False, "score": 0.0, "intent": None}

    # 2. Priority Resolution (Hierarchical)
    # Collect all detected intents
    candidates = []
    if regex_result["detected"]:
        candidates.append({"intent": regex_result["intent"], "score": regex_result["score"], "source": "regex"})
    if semantic_result["detected"]:
        candidates.append({"intent": semantic_result["intent"], "score": semantic_result["score"], "source": "semantic"})
    if zeroshot_result["detected"]:
        candidates.append({"intent": zeroshot_result["intent"], "score": zeroshot_result["score"], "source": "zeroshot"})
    
    # If no candidates, fallback to Unknown
    if not candidates:
        candidates.append({"intent": IntentCategory.UNKNOWN, "score": 0.0, "source": "fallback"})

    primary_intent, primary_score, sorted_candidates = priority_engine.resolve(candidates)
    
    # 3. Risk Calculation (R_total)
    response_data = risk_engine.calculate_risk(
        regex_result=regex_result,
        semantic_result=semantic_result,
        zeroshot_result=zeroshot_result,
        keyword_result=keyword_result
    )
    
    # Update Intent/Tier based on Priority Engine
    response_data.intent = primary_intent
    response_data.tier = TIER_MAPPING.get(primary_intent, IntentTier.P4)

    # 4. Policy Enforcement (Cedar)
    # Map context
    principal = "Role::\"general\""
    
    action_str = "Action::\"query\"" # Default
    if "summarize" in primary_intent.value:
        action_str = "Action::\"summarize\""
    elif "generate" in primary_intent.value:
        action_str = "Action::\"generate\""
    elif "greeting" in primary_intent.value:
        action_str = "Action::\"greet\""
    
    resource = "App::\"IntentAnalyzer\""
    
    context = {
        "risk_score": int(response_data.risk_score * 100),
        "tier": response_data.tier.value,
        "has_critical_signal": response_data.tier == IntentTier.P0,
        "domain": _map_intent_to_domain(primary_intent)
    }
    
    policy_result = policy_engine.evaluate(principal, action_str, resource, context)
    
    response_data.decision = policy_result.decision
    response_data.reason = policy_result.reason
    
    elapsed = round((time.time() - start_time) * 1000, 2)
    response_data.processing_time_ms = elapsed

    # Convert to dict for JSON response
    resp_dict = response_data.dict()

    # Debug trace
    if debug:
        resp_dict["trace"] = {
            "candidates": sorted_candidates,
            "regex": regex_result,
            "semantic": semantic_result,
            "zeroshot": zeroshot_result,
            "r_total": response_data.risk_score,
            "policy": {
                "decision": policy_result.decision,
                "diagnostics": policy_result.diagnostics,
                "context": context
            }
        }

    # Cache Write
    cache_service.set(input_text, resp_dict)

    return resp_dict


@router.get("/health")
def health():
    return {
        "status": "ok",
        "architecture": "tri-axis",
        "classifiers": list(classifiers.keys()),
    }
