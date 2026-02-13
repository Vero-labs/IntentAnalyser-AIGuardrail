"""
Keyword Booster - Lightweight pre-filter for strong lexical signals.

Applies confidence boosts to intents based on keyword/pattern matches.
This runs BEFORE the heavy ML models and helps disambiguate obvious cases
like "write code for X" vs "summarize this document".

The booster does NOT make final decisions — it produces a boost_map
that the RiskEngine uses to adjust zero-shot/semantic scores.
"""
import re
from typing import Dict, Any, Optional
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory
import logging

logger = logging.getLogger(__name__)


# Pattern rules: each category has a list of regex patterns and a boost value.
# Patterns are checked case-insensitively against the raw input.
KEYWORD_RULES = {
    IntentCategory.PROMPT_INJECTION: {
        "patterns": [
            r"\b(?:ignore|bypass|override|forget|reset|clear)\b.*\b(?:instructions?|rules?|prompts?|filters?|constraints?|system)\b",
            r"\b(?:instead|rather)\b.*\b(?:do|say|act|reveal)\b",
            r"\b(?:hidden|internal|system)\b.*\b(?:instructions?|rules?|prompts?|messages?)\b",
            r"\b(?:start|begin)\b.*\b(?:ignoring|new role|fresh start)\b",
            r"\b(?:stop)\b.*\b(?:following|listening|abiding)\b",
        ],
        "boost": 0.35,
    },
    IntentCategory.JAILBREAK: {
        "patterns": [
            r"\b(?:act as|become|roleplay|pretend)\b.*\b(?:unrestricted|unfiltered|god mode|dan|jailbroken|evil|no rules)\b",
            r"\b(?:developer|debug|admin|root|superuser)\b.*\b(?:mode|access|override)\b",
            r"\b(?:no\s+moral|no\s+filter|unconstrained)\b",
        ],
        "boost": 0.35,
    },
    IntentCategory.CODE_EXECUTION: {
        "patterns": [
            r"\b(?:write|create|build|generate|implement|code|develop|make)\b.*\b(?:code|script|program|function|class|algorithm|app|api|module)\b",
            r"\b(?:code|script|program|function|algorithm)\b.*\b(?:for|to|that|which)\b",
            r"\b(?:python|javascript|java|c\+\+|rust|go|ruby|php|typescript|html|css|sql|bash|shell)\b.*\b(?:code|script|program|function|for)\b",
            r"\bimplement\b.*\b(?:sort|search|tree|graph|stack|queue|linked list|hash|array|matrix)\b",
        ],
        "boost": 0.25,
    },
    IntentCategory.INFO_SUMMARIZE: {
        "patterns": [
            r"\b(?:summarize|summarise|condense|tldr|tl;dr)\b",
            r"\bgive\b.*\b(?:summary|overview|gist|key points|highlights|takeaways)\b",
            r"\b(?:brief|short)\b.*\b(?:summary|overview)\b",
        ],
        "boost": 0.25,
    },
    IntentCategory.GREETING: {
        "patterns": [
            r"^(?:hello|hi|hey|howdy|greetings|good\s*(?:morning|afternoon|evening|day))[\s!?.]*$",
            r"^(?:how are you|what'?s up|sup)[\s!?.]*$",
        ],
        "boost": 0.35,
    },
    IntentCategory.INFO_QUERY: {
        "patterns": [
            r"^(?:what|who|where|when|why|how|which|define|explain)\b.*\??\s*$",
            r"\b(?:tell me|give me|what is|who is|where is|how does)\b.*\b(?:about|the|of)\b",
        ],
        "boost": 0.15,
    },
    IntentCategory.OFF_TOPIC: {
        "patterns": [
            r"\b(?:write|tell|compose|sing)\b.*\b(?:poem|story|joke|song|haiku|limerick)\b",
            r"\b(?:recipe|how to (?:cook|bake))\b",
            r"\b(?:game|play|football|movie|celebrity|hobby)\b",
        ],
        "boost": 0.15,
    },
}

# Pre-compile all patterns
_COMPILED_RULES = {}
for intent, rule in KEYWORD_RULES.items():
    _COMPILED_RULES[intent] = {
        "patterns": [re.compile(p, re.IGNORECASE) for p in rule["patterns"]],
        "boost": rule["boost"],
    }


class KeywordBooster(BaseDetector):
    """
    Fast keyword-based pre-filter that produces boost scores for each intent.
    These boosts are used by the RiskEngine to adjust ML model predictions.
    """

    def __init__(self):
        pass

    async def load(self):
        logger.info(f"KeywordBooster loaded with {len(_COMPILED_RULES)} intent rules.")

    def detect(self, text: str) -> Dict[str, Any]:
        """
        Returns a boost_map: {IntentCategory: boost_value} for all matching patterns.
        Also returns the single strongest match as the primary result.
        """
        boost_map: Dict[IntentCategory, float] = {}
        match_details = {}

        for intent, rule in _COMPILED_RULES.items():
            for pattern in rule["patterns"]:
                if pattern.search(text):
                    boost_map[intent] = rule["boost"]
                    match_details[intent.value] = pattern.pattern
                    break  # One match per category is enough

        if boost_map:
            # Pick the strongest boost as the primary
            best_intent = max(boost_map, key=boost_map.get)
            best_boost = boost_map[best_intent]
            logger.info(f"KeywordBooster: {len(boost_map)} matches, best={best_intent.value} (+{best_boost:.2f})")
            return {
                "detected": True,
                "score": best_boost,
                "intent": best_intent,
                "metadata": {
                    "boost_map": {k.value: v for k, v in boost_map.items()},
                    "match_details": match_details,
                }
            }

        return {
            "detected": False,
            "score": 0.0,
            "intent": None,
            "metadata": {"boost_map": {}}
        }
