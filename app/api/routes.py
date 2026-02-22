"""
Tri-Axis Intent Analyzer — API Routes.

Pipeline:
  1. Deterministic risk routing (regex + lexicons + keyword checks)
  2. Fast-safe bypass for trivial benign prompts
  3. Zero-shot detector (only if deterministic routing is inconclusive)
  4. Tier mapping
  5. Classic YAML policy enforcement (main.yaml)

Output is deterministic: intent, confidence, tier, decision.
Trace available via ?debug=true.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from app.schemas.intent import AnalysisBreakdown, IntentRequest, IntentResponse
from app.services.detectors.zeroshot import ZeroShotDetector
from app.core.cache import CacheService
from app.core.rate_limit import RateLimiter
from app.services.priority_engine import PriorityEngine
from app.services.detectors.regex import RegexDetector
from app.services.classic_policy import (
    ClassicPolicyError,
    POLICY_PATH,
    evaluate_classic_policy,
    load_classic_policy,
)
from app.core.taxonomy import IntentCategory, IntentTier
from typing import Dict, Any
import logging
import os
import time
import re

router = APIRouter()
logger = logging.getLogger(__name__)

classifiers = {}
cache_service = CacheService()
rate_limiter = RateLimiter(requests_per_minute=6000)

@router.on_event("startup")
async def startup_event():
    logger.info("Initializing Classifiers...")
    classifiers["regex"] = RegexDetector()
    classifiers["zeroshot"] = ZeroShotDetector()
    
    await classifiers["regex"].load()
    await classifiers["zeroshot"].load()
    logger.info("Classifiers Initialized.")

# Engines
priority_engine = PriorityEngine()

OVERRIDE_INTENTS = {
    IntentCategory.PROMPT_INJECTION,
    IntentCategory.JAILBREAK,
    IntentCategory.SYSTEM_OVERRIDE,
}

TIER_RANK: Dict[IntentTier, int] = {
    IntentTier.P0: 0,
    IntentTier.P1: 1,
    IntentTier.P2: 2,
    IntentTier.P3: 3,
    IntentTier.P4: 4,
}
RANK_TO_TIER: Dict[int, IntentTier] = {v: k for k, v in TIER_RANK.items()}
RISK_SCORE_BY_TIER: Dict[IntentTier, float] = {
    IntentTier.P0: 1.0,
    IntentTier.P1: 0.85,
    IntentTier.P2: 0.65,
    IntentTier.P3: 0.45,
    IntentTier.P4: 0.0,
}

TOXICITY_THRESHOLD = 0.6
FINANCIAL_THRESHOLD = 0.5
LOW_CONFIDENCE_THRESHOLD = 0.4
FAST_SAFE_MAX_CHARS = 200
FAST_SAFE_MAX_TOKENS = 24
FAST_SAFE_CONFIDENCE = 0.6
TOXICITY_POLICY_MODE = os.getenv("TOXICITY_POLICY_MODE", "block").strip().lower()
if TOXICITY_POLICY_MODE not in {"block", "warn", "log"}:
    TOXICITY_POLICY_MODE = "block"

PII_PATTERN_DEFINITIONS = [
    ("ssn_phrase", re.compile(r"\bsocial\s+security\s+number\b", re.IGNORECASE)),
    ("ssn_compact", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card_phrase", re.compile(r"\bcredit\s*card\b", re.IGNORECASE)),
    ("api_keys_phrase", re.compile(r"\b(api[_\s-]?keys?|secret\s+keys?)\b", re.IGNORECASE)),
    ("password_phrase", re.compile(r"\b(passwords?|passwd|credentials?)\b", re.IGNORECASE)),
    ("private_key_phrase", re.compile(r"\bprivate\s+keys?\b", re.IGNORECASE)),
    ("database_dump_phrase", re.compile(r"\bdump\s+(the\s+)?(database|db)\b", re.IGNORECASE)),
    ("user_email_dump_phrase", re.compile(r"\b(show|list|dump).{0,20}\buser\s+emails?\b", re.IGNORECASE)),
]

TOXICITY_LEXICON_PATTERNS = [
    ("useless", re.compile(r"\buseless\b", re.IGNORECASE)),
    ("stupid", re.compile(r"\bstupid\b", re.IGNORECASE)),
    ("shut_up", re.compile(r"\bshut\s+up\b", re.IGNORECASE)),
    ("idiot", re.compile(r"\bidiot\b", re.IGNORECASE)),
    ("moron", re.compile(r"\bmoron\b", re.IGNORECASE)),
    ("worthless", re.compile(r"\bworthless\b", re.IGNORECASE)),
    ("dumb", re.compile(r"\bdumb\b", re.IGNORECASE)),
    ("loser", re.compile(r"\bloser\b", re.IGNORECASE)),
    ("hate_you", re.compile(r"\bhate you\b", re.IGNORECASE)),
]

TOXICITY_PATTERN_DETECTIONS = [
    ("you_are_insult", re.compile(r"\byou\s+are\s+(an?\s+)?(idiot|stupid|useless|worthless|moron|dumb|pathetic|trash)\b", re.IGNORECASE)),
    ("second_person_harassment", re.compile(r"\b(you|your)\s+(are|re|seem)\s+(awful|terrible|garbage|trash)\b", re.IGNORECASE)),
    ("command_silence", re.compile(r"\b(shut\s+up|be\s+quiet)\b", re.IGNORECASE)),
]

FINANCIAL_KEYWORD_PATTERNS = [
    ("stock", re.compile(r"\bstocks?\b", re.IGNORECASE)),
    ("crypto", re.compile(r"\bcrypto(currency)?\b", re.IGNORECASE)),
    ("investment", re.compile(r"\binvest(ment|ing)?\b", re.IGNORECASE)),
    ("trading", re.compile(r"\btrading?\b", re.IGNORECASE)),
    ("market_prediction", re.compile(r"\bmarket\s+(prediction|forecast|trend)\b", re.IGNORECASE)),
]

OVERRIDE_KEYWORD_PATTERNS = [
    re.compile(r"\b(ignore|bypass|override|jailbreak|dan)\b", re.IGNORECASE),
    re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(reveal|leak)\s+(system|hidden|internal)\b", re.IGNORECASE),
]

SYSTEM_INSTRUCTION_VERB_PATTERNS = [
    re.compile(r"\b(ignore|forget|reveal|disable|reset|override|bypass|execute)\b", re.IGNORECASE),
    re.compile(r"\bfrom\s+now\s+on\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\b", re.IGNORECASE),
]

MULTILINE_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)

SAFE_MATH_QUERY_PATTERNS = [
    re.compile(r"^\s*what\s+is\s+[-+*/\d\.\s\(\)=%]+\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*calculate\s+[-+*/\d\.\s\(\)=%]+\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+(\.\d+)?\s*[-+*/]\s*\d+(\.\d+)?\s*$", re.IGNORECASE),
]

SAFE_FACTUAL_QUERY_PATTERNS = [
    re.compile(r"^\s*(who|what|when|where|why|how)\b.{1,180}\?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(is|are|can|does|do)\b.{1,170}\?\s*$", re.IGNORECASE),
]

SAFE_DEFINITION_PATTERNS = [
    re.compile(r"^\s*define\s+.{1,160}$", re.IGNORECASE),
    re.compile(r"^\s*what\s+does\s+.{1,140}\s+mean\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*definition\s+of\s+.{1,150}$", re.IGNORECASE),
]

SAFE_CONVERSION_PATTERNS = [
    re.compile(r"^\s*convert\s+.{1,150}\s+to\s+.{1,80}[\.?]?\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(convert\s+)?\d+(\.\d+)?\s*(degrees?\s*)?"
        r"(celsius|fahrenheit|kelvin)\s+to\s+(degrees?\s*)?"
        r"(celsius|fahrenheit|kelvin)[\.?]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(what\s+is\s+)?\d+(\.\d+)?\s*(degrees?\s*)?"
        r"(celsius|fahrenheit|kelvin)\s+in\s+(degrees?\s*)?"
        r"(celsius|fahrenheit|kelvin)\??\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*convert\s+\d+(\.\d+)?\s*(km|kilometers?|m|meters?|mi|miles?|kg|kilograms?|lb|pounds?|cm|mm|inches?|ft)\s+"
        r"to\s+(km|kilometers?|m|meters?|mi|miles?|kg|kilograms?|lb|pounds?|cm|mm|inches?|ft)[\.?]?\s*$",
        re.IGNORECASE,
    ),
]

SAFE_ARITHMETIC_PATTERNS = [
    re.compile(r"^\s*(add|subtract|multiply|divide)\s+\d+(\.\d+)?(\s+and\s+\d+(\.\d+)?)?[\.?]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+is\s+the\s+(sum|difference|product|quotient)\s+of\s+\d+(\.\d+)?\s+and\s+\d+(\.\d+)?\??\s*$", re.IGNORECASE),
]

BENIGN_INTENT_HINTS = {
    IntentCategory.INFO_QUERY,
    IntentCategory.INFO_SUMMARIZE,
    IntentCategory.TOOL_AUTHORIZED,
    IntentCategory.GREETING,
}

SENSITIVE_MODEL_HINT_INTENTS = {
    IntentCategory.PROMPT_INJECTION,
    IntentCategory.JAILBREAK,
    IntentCategory.SYSTEM_OVERRIDE,
    IntentCategory.PII_EXFILTRATION,
    IntentCategory.TOOL_MISUSE,
    IntentCategory.TOXICITY,
    IntentCategory.FINANCIAL_ADVICE,
}

NEGATIVE_SENTIMENT_WORDS = {
    "bad", "hate", "awful", "terrible", "worst", "stupid", "idiot",
    "moron", "dumb", "useless", "worthless", "garbage", "trash", "pathetic",
}
POSITIVE_SENTIMENT_WORDS = {"good", "great", "thanks", "thank", "nice", "helpful", "please"}


def _clamp_01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _has_pattern(text: str, patterns: list[re.Pattern]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _extract_intent_score(result: Dict[str, Any], intent: IntentCategory) -> float:
    metadata = result.get("metadata") if isinstance(result, dict) else None
    if isinstance(metadata, dict):
        all_scores = metadata.get("all_scores")
        if isinstance(all_scores, dict):
            score = all_scores.get(intent.value)
            if isinstance(score, (int, float)):
                return _clamp_01(score)

    if isinstance(result, dict) and result.get("intent") == intent:
        return _clamp_01(result.get("score", 0.0))

    return 0.0


def _empty_detector_result() -> Dict[str, Any]:
    return {"detected": False, "score": 0.0, "intent": None, "metadata": {}}


def _detect_pii_patterns(text: str) -> Dict[str, Any]:
    matches = []
    for name, pattern in PII_PATTERN_DEFINITIONS:
        if pattern.search(text):
            matches.append(name)

    if not matches:
        return {"detected": False, "score": 0.0, "intent": None, "metadata": {}}

    return {
        "detected": True,
        "score": 1.0,
        "intent": IntentCategory.PII_EXFILTRATION,
        "metadata": {"patterns": matches},
    }


def _detect_toxicity_lexicon(text: str) -> Dict[str, Any]:
    lexicon_hits = []
    for name, pattern in TOXICITY_LEXICON_PATTERNS:
        if pattern.search(text):
            lexicon_hits.append(name)

    pattern_hits = []
    for name, pattern in TOXICITY_PATTERN_DETECTIONS:
        if pattern.search(text):
            pattern_hits.append(name)

    sentiment_score = _sentiment_polarity(text)

    toxicity_score = 0.0
    if pattern_hits:
        toxicity_score = max(toxicity_score, 0.85)
    if lexicon_hits:
        toxicity_score = max(toxicity_score, min(0.45 + 0.15 * len(lexicon_hits), 0.85))
    if sentiment_score >= 0.25:
        toxicity_score = max(toxicity_score, 0.65)
    if sentiment_score >= 0.4:
        toxicity_score = max(toxicity_score, 0.8)

    detected = toxicity_score >= TOXICITY_THRESHOLD
    if not detected:
        return {
            "detected": False,
            "score": float(_clamp_01(toxicity_score)),
            "intent": None,
            "metadata": {
                "lexicon_hits": lexicon_hits,
                "pattern_hits": pattern_hits,
                "sentiment_polarity": round(sentiment_score, 4),
            },
        }

    return {
        "detected": True,
        "score": float(_clamp_01(toxicity_score)),
        "intent": IntentCategory.TOXICITY,
        "metadata": {
            "lexicon_hits": lexicon_hits,
            "pattern_hits": pattern_hits,
            "sentiment_polarity": round(sentiment_score, 4),
        },
    }


def _detect_financial_keywords(text: str) -> Dict[str, Any]:
    matches = []
    for name, pattern in FINANCIAL_KEYWORD_PATTERNS:
        if pattern.search(text):
            matches.append(name)

    if not matches:
        return {"detected": False, "score": 0.0, "intent": None, "metadata": {}}

    return {
        "detected": True,
        "score": 0.8,
        "intent": IntentCategory.FINANCIAL_ADVICE,
        "metadata": {"patterns": matches},
    }


def _sentiment_polarity(text: str) -> float:
    words = re.findall(r"\b[a-z']+\b", text.lower())
    if not words:
        return 0.0
    neg = sum(1 for word in words if word in NEGATIVE_SENTIMENT_WORDS)
    pos = sum(1 for word in words if word in POSITIVE_SENTIMENT_WORDS)
    return float((neg - pos) / len(words))


def _matches_safe_prompt_pattern(text: str) -> bool:
    if any(pattern.match(text) for pattern in SAFE_MATH_QUERY_PATTERNS):
        return True
    if any(pattern.match(text) for pattern in SAFE_CONVERSION_PATTERNS):
        return True
    if any(pattern.match(text) for pattern in SAFE_ARITHMETIC_PATTERNS):
        return True
    if any(pattern.match(text) for pattern in SAFE_FACTUAL_QUERY_PATTERNS):
        return True
    if any(pattern.match(text) for pattern in SAFE_DEFINITION_PATTERNS):
        return True
    # Very short neutral question form (conservative)
    return bool(
        re.match(r"^\s*[A-Za-z0-9][A-Za-z0-9\s\?\.,'\":\-\+\*/=%\(\)]{2,120}\?\s*$", text)
        and not re.search(r"\b(ignore|override|bypass|reveal|hack|steal)\b", text, re.IGNORECASE)
    )


def _is_fast_safe_candidate(
    text: str,
    regex_result: Dict[str, Any],
    pii_pattern_result: Dict[str, Any],
    toxicity_lexicon_result: Dict[str, Any],
    financial_keyword_result: Dict[str, Any],
) -> bool:
    if regex_result.get("detected"):
        return False
    if pii_pattern_result.get("detected"):
        return False
    if toxicity_lexicon_result.get("detected"):
        return False
    if financial_keyword_result.get("detected"):
        return False
    if len(text) > FAST_SAFE_MAX_CHARS:
        return False
    if len(text.split()) > FAST_SAFE_MAX_TOKENS:
        return False
    if _has_pattern(text, OVERRIDE_KEYWORD_PATTERNS):
        return False
    if _has_pattern(text, SYSTEM_INSTRUCTION_VERB_PATTERNS):
        return False
    if MULTILINE_CODE_BLOCK_PATTERN.search(text):
        return False
    if not _matches_safe_prompt_pattern(text):
        return False

    return bool(re.match(r"^[\w\s\?\.,'\":\-\+\*/=%\(\)]+$", text))


def _build_signal_contract(
    regex_result: Dict[str, Any],
    pii_pattern_result: Dict[str, Any],
    toxicity_lexicon_result: Dict[str, Any],
    financial_keyword_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    zeroshot_result: Dict[str, Any],
    primary_intent: IntentCategory,
    primary_score: float,
    deterministic_safe_signal: bool,
) -> Dict[str, Any]:
    override_sem_zs_score = max(
        max(_extract_intent_score(semantic_result, intent), _extract_intent_score(zeroshot_result, intent))
        for intent in OVERRIDE_INTENTS
    )

    override_detected = (
        bool(regex_result.get("detected"))
        and regex_result.get("intent") in OVERRIDE_INTENTS
    ) or override_sem_zs_score >= 0.5

    pii_score = max(
        _extract_intent_score(semantic_result, IntentCategory.PII_EXFILTRATION),
        _extract_intent_score(zeroshot_result, IntentCategory.PII_EXFILTRATION),
    )
    pii_detected = (
        bool(regex_result.get("detected"))
        and regex_result.get("intent") == IntentCategory.PII_EXFILTRATION
    ) or bool(pii_pattern_result.get("detected")) or pii_score >= 0.5

    toxicity_score = max(
        _clamp_01(toxicity_lexicon_result.get("score", 0.0)),
        _extract_intent_score(semantic_result, IntentCategory.TOXICITY),
        _extract_intent_score(zeroshot_result, IntentCategory.TOXICITY),
    )
    financial_advice_score = max(
        _clamp_01(financial_keyword_result.get("score", 0.0)),
        _extract_intent_score(semantic_result, IntentCategory.FINANCIAL_ADVICE),
        _extract_intent_score(zeroshot_result, IntentCategory.FINANCIAL_ADVICE),
    )
    confidence = _clamp_01(primary_score)
    raw_low_confidence = bool(confidence < LOW_CONFIDENCE_THRESHOLD)
    benign_hint_detected = bool(primary_intent in BENIGN_INTENT_HINTS)
    zeroshot_intent = zeroshot_result.get("intent")
    sensitive_model_hint = bool(
        zeroshot_intent in SENSITIVE_MODEL_HINT_INTENTS
        and _clamp_01(zeroshot_result.get("score", 0.0)) > 0.0
    )
    risk_aware_low_confidence = bool(
        raw_low_confidence
        and not deterministic_safe_signal
        and not benign_hint_detected
        and sensitive_model_hint
    )

    contract = {
        "override_detected": bool(override_detected),
        "pii_detected": bool(pii_detected),
        "toxicity_detected": bool(toxicity_score >= TOXICITY_THRESHOLD),
        "toxicity_enforce_block": bool(TOXICITY_POLICY_MODE == "block"),
        "financial_advice_detected": bool(financial_advice_score >= FINANCIAL_THRESHOLD),
        "low_confidence": risk_aware_low_confidence,
        "low_confidence_raw": raw_low_confidence,
        "deterministic_safe_signal": bool(deterministic_safe_signal),
        "benign_hint_detected": benign_hint_detected,
        "sensitive_model_hint": sensitive_model_hint,
        "toxicity_score": _clamp_01(toxicity_score),
        "financial_advice_score": _clamp_01(financial_advice_score),
        "confidence": confidence,
        "intent": primary_intent.value,
    }
    return contract


def _validate_signal_contract(signal_contract: Dict[str, Any]) -> None:
    required_boolean_fields = [
        "override_detected",
        "pii_detected",
        "toxicity_detected",
        "toxicity_enforce_block",
        "financial_advice_detected",
        "low_confidence",
        "low_confidence_raw",
        "deterministic_safe_signal",
        "benign_hint_detected",
        "sensitive_model_hint",
    ]
    required_score_fields = [
        "toxicity_score",
        "financial_advice_score",
        "confidence",
    ]
    for field in required_boolean_fields:
        value = signal_contract.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"'{field}' must be bool, got {type(value).__name__}")

    for field in required_score_fields:
        value = signal_contract.get(field)
        if not isinstance(value, (int, float)):
            raise ValueError(f"'{field}' must be numeric in [0,1], got {type(value).__name__}")
        if value < 0.0 or value > 1.0:
            raise ValueError(f"'{field}' out of range [0,1]: {value}")

    intent_value = signal_contract.get("intent")
    if not isinstance(intent_value, str) or not intent_value:
        raise ValueError("'intent' must be a non-empty string")


def _derive_final_tier(signal_contract: Dict[str, Any], user_role: str) -> tuple[IntentTier, int, bool]:
    tier_rank = 4  # P4 default

    if signal_contract["override_detected"]:
        tier_rank = min(tier_rank, 0)
    if signal_contract["pii_detected"]:
        tier_rank = min(tier_rank, 1)
    if signal_contract["toxicity_detected"]:
        tier_rank = min(tier_rank, 2)
    if signal_contract["financial_advice_detected"]:
        tier_rank = min(tier_rank, 3)

    low_confidence_clamp = signal_contract["low_confidence"] and user_role != "admin"
    if low_confidence_clamp:
        tier_rank = min(tier_rank, 3)

    return RANK_TO_TIER[tier_rank], tier_rank, low_confidence_clamp


@router.post("/intent", dependencies=[Depends(rate_limiter)])
async def analyze_intent(request: IntentRequest, debug: bool = Query(False)):
    total_start = time.perf_counter()
    stage_timings = {
        "regex_ms": 0.0,
        "semantic_ms": 0.0,
        "zeroshot_ms": 0.0,
        "policy_eval_ms": 0.0,
        "total_ms": 0.0,
    }
    pii_pattern_ms = 0.0
    toxicity_lexicon_ms = 0.0
    financial_keyword_ms = 0.0

    # Input normalization
    input_text = request.text
    if not input_text and request.messages:
        input_text = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
    if not input_text:
        raise HTTPException(status_code=400, detail="Text or messages required")

    # Cache lookup
    # Include role in cache key to prevent context poisoning between roles
    role = request.user_role or "general"
    cache_key = f"{role}:{input_text}"

    # For timing/debug investigations we bypass cache to expose real stage timings.
    if not debug:
        cached = cache_service.get(cache_key)
        if cached:
            cached["processing_time_ms"] = round((time.perf_counter() - total_start) * 1000, 2)
            return cached

    # 1. Regex detector (cheap)
    stage_start = time.perf_counter()
    regex_result = classifiers["regex"].detect(input_text)
    stage_timings["regex_ms"] = round((time.perf_counter() - stage_start) * 1000, 3)

    regex_p0_immediate = bool(
        regex_result.get("detected")
        and regex_result.get("intent") in OVERRIDE_INTENTS
    )
    if regex_p0_immediate:
        logger.info("Regex P0 immediate path detected. Skipping all additional detection stages.")

    pii_pattern_result = _empty_detector_result()
    toxicity_lexicon_result = _empty_detector_result()
    financial_keyword_result = _empty_detector_result()

    if not regex_p0_immediate:
        # 2. Deterministic PII pattern detector (cheap)
        stage_start = time.perf_counter()
        pii_pattern_result = _detect_pii_patterns(input_text)
        pii_pattern_ms = round((time.perf_counter() - stage_start) * 1000, 3)

        # 3. Deterministic toxicity lexicon detector (cheap)
        stage_start = time.perf_counter()
        toxicity_lexicon_result = _detect_toxicity_lexicon(input_text)
        toxicity_lexicon_ms = round((time.perf_counter() - stage_start) * 1000, 3)

        # 4. Deterministic financial keyword detector (cheap)
        stage_start = time.perf_counter()
        financial_keyword_result = _detect_financial_keywords(input_text)
        financial_keyword_ms = round((time.perf_counter() - stage_start) * 1000, 3)

    semantic_result = _empty_detector_result()
    zeroshot_result = _empty_detector_result()

    # 5. Candidate gathering + deterministic risk checks
    candidates = []
    deterministic_high_severity = False
    deterministic_medium_severity = False
    fast_safe_path = False
    safe_pattern_hint = _matches_safe_prompt_pattern(input_text)

    if regex_result["detected"]:
        candidates.append({"intent": regex_result["intent"], "score": regex_result["score"], "source": "regex"})

        if regex_result["intent"] in OVERRIDE_INTENTS or regex_result["intent"] == IntentCategory.PII_EXFILTRATION:
            deterministic_high_severity = True

    if pii_pattern_result["detected"]:
        candidates.append(
            {
                "intent": pii_pattern_result["intent"],
                "score": pii_pattern_result["score"],
                "source": "pii_regex",
            }
        )
        deterministic_medium_severity = True

    if toxicity_lexicon_result["detected"]:
        candidates.append(
            {
                "intent": toxicity_lexicon_result["intent"],
                "score": toxicity_lexicon_result["score"],
                "source": "toxicity_lexicon",
            }
        )
        deterministic_medium_severity = True

    if financial_keyword_result["detected"]:
        candidates.append(
            {
                "intent": financial_keyword_result["intent"],
                "score": financial_keyword_result["score"],
                "source": "financial_keywords",
            }
        )
        deterministic_medium_severity = True

    # 6. Fast safe path (skip expensive inference on trivial benign prompts)
    if not deterministic_high_severity and not deterministic_medium_severity and _is_fast_safe_candidate(
        input_text,
        regex_result,
        pii_pattern_result,
        toxicity_lexicon_result,
        financial_keyword_result,
    ):
        fast_safe_path = True
        candidates.append(
            {
                "intent": IntentCategory.INFO_QUERY,
                "score": FAST_SAFE_CONFIDENCE,
                "source": "safe_fast_path",
            }
        )
        logger.info("Fast safe path: skipped semantic and zeroshot for trivial benign prompt.")

    # 7. Expensive detector (zeroshot only) when no deterministic routing applies
    if not deterministic_high_severity and not deterministic_medium_severity and not fast_safe_path:
        stage_start = time.perf_counter()
        zeroshot_result = classifiers["zeroshot"].detect(input_text)
        stage_timings["zeroshot_ms"] = round((time.perf_counter() - stage_start) * 1000, 3)
        if zeroshot_result["detected"]:
            candidates.append(
                {"intent": zeroshot_result["intent"], "score": zeroshot_result["score"], "source": "zeroshot"}
            )
    elif deterministic_high_severity:
        logger.info("Early exit path: regex P0/P1 signal detected, skipped semantic and zeroshot.")
    elif deterministic_medium_severity:
        logger.info("Deterministic medium-risk path: skipped semantic and zeroshot.")

    if not candidates:
        candidates.append({"intent": IntentCategory.UNKNOWN, "score": 0.0, "source": "fallback"})

    # 7. Hierarchical priority resolution
    primary_intent, primary_score, sorted_candidates = priority_engine.resolve(candidates)

    signal_contract = _build_signal_contract(
        regex_result=regex_result,
        pii_pattern_result=pii_pattern_result,
        toxicity_lexicon_result=toxicity_lexicon_result,
        financial_keyword_result=financial_keyword_result,
        semantic_result=semantic_result,
        zeroshot_result=zeroshot_result,
        primary_intent=primary_intent,
        primary_score=primary_score,
        deterministic_safe_signal=bool(fast_safe_path or safe_pattern_hint),
    )

    try:
        _validate_signal_contract(signal_contract)
    except ValueError as exc:
        logger.error("Signal contract invariant violation: %s | contract=%s", exc, signal_contract)
        if debug:
            raise
        raise HTTPException(status_code=500, detail=f"Signal contract invariant violation: {exc}")

    final_tier, final_tier_rank, low_confidence_clamp = _derive_final_tier(signal_contract, role)

    # 8. Build deterministic response payload
    response_data = IntentResponse(
        intent=primary_intent,
        confidence=_clamp_01(primary_score),
        risk_score=RISK_SCORE_BY_TIER[final_tier],
        tier=final_tier,
        breakdown=AnalysisBreakdown(
            regex_match=bool(regex_result.get("detected")),
            semantic_score=_clamp_01(semantic_result.get("score", 0.0)),
            zeroshot_score=_clamp_01(zeroshot_result.get("score", 0.0)),
            detected_tier=final_tier,
        ),
    )

    # 9. Classic policy enforcement from app/policies/main.yaml
    stage_start = time.perf_counter()
    try:
        classic_policy = load_classic_policy(POLICY_PATH)
    except ClassicPolicyError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid policy file: {exc}") from exc
    policy_eval = evaluate_classic_policy(
        classic_policy,
        role=role,
        detected_intent=primary_intent.value,
        confidence=response_data.confidence,
        text=input_text,
    )
    stage_timings["policy_eval_ms"] = round((time.perf_counter() - stage_start) * 1000, 3)

    response_data.decision = policy_eval["decision"]
    response_data.reason = policy_eval["reason"]

    if signal_contract["toxicity_detected"] and response_data.decision == "allow":
        if TOXICITY_POLICY_MODE == "warn":
            response_data.reason = f"{response_data.reason} | Toxicity detected (warn mode)."
        elif TOXICITY_POLICY_MODE == "log":
            logger.warning(
                "Toxicity detected in log mode; allowing request. intent=%s text_preview=%s",
                response_data.intent.value,
                input_text[:120],
            )

    stage_timings["total_ms"] = round((time.perf_counter() - total_start) * 1000, 2)
    response_data.processing_time_ms = stage_timings["total_ms"]

    # Convert to dict for JSON response
    resp_dict = response_data.dict()

    logger.info(
        "Intent pipeline timings (ms): regex=%s semantic=%s zeroshot=%s policy=%s total=%s",
        stage_timings["regex_ms"],
        stage_timings["semantic_ms"],
        stage_timings["zeroshot_ms"],
        stage_timings["policy_eval_ms"],
        stage_timings["total_ms"],
    )

    # Debug trace
    if debug:
        resp_dict["trace"] = {
            "pipeline": {
                "regex_p0_immediate": regex_p0_immediate,
                "deterministic_high_severity": deterministic_high_severity,
                "deterministic_medium_severity": deterministic_medium_severity,
                "fast_safe_path": fast_safe_path,
                "safe_pattern_hint": safe_pattern_hint,
                "toxicity_policy_mode": TOXICITY_POLICY_MODE,
                "pii_regex_ms": pii_pattern_ms,
                "toxicity_lexicon_ms": toxicity_lexicon_ms,
                "financial_keyword_ms": financial_keyword_ms,
            },
            "timings_ms": stage_timings,
            "candidates": sorted_candidates,
            "regex": regex_result,
            "pii_regex": pii_pattern_result,
            "financial_keywords": financial_keyword_result,
            "semantic": semantic_result,
            "zeroshot": zeroshot_result,
            "signal_contract": signal_contract,
            "tier_mapping": {
                "tier": final_tier.value,
                "tier_rank": final_tier_rank,
                "low_confidence_clamp": low_confidence_clamp,
            },
            "r_total": response_data.risk_score,
            "policy": {
                "decision": response_data.decision,
                "reason": response_data.reason,
                "policy_intent": policy_eval.get("policy_intent"),
                "policy_path": str(POLICY_PATH),
            }
        }

    # Cache result (TTL 60s)
    if not debug:
        cache_service.set(cache_key, resp_dict)
    
    return resp_dict


@router.get("/health")
def health():
    return {
        "status": "ok",
        "architecture": "tri-axis",
        "classifiers": list(classifiers.keys()),
    }
