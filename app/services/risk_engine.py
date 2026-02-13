from typing import List, Dict, Any, Optional
from app.core.taxonomy import IntentCategory, IntentTier, TIER_MAPPING
from app.schemas.intent import AnalysisBreakdown, IntentResponse
import logging

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self):
        # Weights for the ensemble
        self.weights = {
            "regex": 0.0,     # Override-based, not weighted
            "keyword": 0.0,   # Boost-based, not weighted
            "semantic": 0.3,
            "zeroshot": 0.7
        }
        
        # Risk baselines per Tier
        self.tier_risk_baseline = {
            IntentTier.CRITICAL: 1.0,
            IntentTier.HIGH: 0.8,
            IntentTier.MEDIUM: 0.5,
            IntentTier.LOW: 0.1
        }

    def calculate_risk(
        self, 
        regex_result: Dict, 
        semantic_result: Dict, 
        zeroshot_result: Dict,
        keyword_result: Optional[Dict] = None
    ) -> IntentResponse:
        """
        Aggregates results from all detectors to produce a final IntentResponse.
        
        Pipeline priority:
        1. Regex match → instant override (score=1.0)
        2. Keyword + ZeroShot + Semantic → weighted ensemble with boost adjustment
        """
        keyword_result = keyword_result or {"detected": False, "score": 0.0, "intent": None, "metadata": {"boost_map": {}}}
        
        # 1. Deterministic Override (Omega) — Regex
        if regex_result.get("detected"):
            primary_intent = regex_result["intent"]
            risk_score = 1.0
            confidence = 1.0
            breakdown = AnalysisBreakdown(
                regex_match=True,
                semantic_score=semantic_result.get("score", 0.0),
                zeroshot_score=zeroshot_result.get("score", 0.0),
                detected_tier=TIER_MAPPING.get(primary_intent, IntentTier.CRITICAL)
            )
            return IntentResponse(
                intent=primary_intent,
                confidence=confidence,
                risk_score=risk_score,
                tier=breakdown.detected_tier,
                breakdown=breakdown
            )

        # 2. Weighted Ensemble with Keyword Boosting
        semantic_score = semantic_result.get("score", 0.0)
        zeroshot_score = zeroshot_result.get("score", 0.0)
        
        # Start with ZeroShot as the primary label (most accurate for classification)
        primary_intent = zeroshot_result.get("intent") or IntentCategory.UNKNOWN
        primary_confidence = zeroshot_score
        
        # --- Keyword Boost Logic ---
        # If keyword booster detected the SAME intent as ZeroShot, reinforce confidence
        # If keyword booster detected a DIFFERENT intent with strong boost, consider override
        boost_map = keyword_result.get("metadata", {}).get("boost_map", {})
        keyword_intent = keyword_result.get("intent")
        keyword_boost = keyword_result.get("score", 0.0)
        
        if keyword_intent and keyword_boost > 0:
            if keyword_intent == primary_intent:
                # Reinforce: ZeroShot agrees with keyword signal
                primary_confidence = min(1.0, primary_confidence + keyword_boost)
                logger.info(f"Keyword reinforces ZeroShot: {primary_intent.value} boosted to {primary_confidence:.3f}")
            elif keyword_boost >= 0.20:
                # Keyword has a strong signal for a different intent
                # Check if this intent also has decent ZeroShot support
                zeroshot_all_scores = zeroshot_result.get("metadata", {}).get("all_scores", {})
                keyword_zs_score = zeroshot_all_scores.get(keyword_intent.value, 0.0) if isinstance(zeroshot_all_scores, dict) else 0.0
                
                # If keyword intent has at least some ZeroShot signal (>0.05), and the 
                # boost is strong, override the primary
                if keyword_zs_score > 0.05 or keyword_boost >= 0.25:
                    # Only override if the boosted score would actually be higher
                    effective_keyword_score = keyword_zs_score + keyword_boost
                    if effective_keyword_score > primary_confidence:
                        logger.info(
                            f"Keyword override: {keyword_intent.value} "
                            f"(boost={keyword_boost:.2f} + zs={keyword_zs_score:.3f} = {effective_keyword_score:.3f}) "
                            f"> {primary_intent.value} ({primary_confidence:.3f})"
                        )
                        primary_intent = keyword_intent
                        primary_confidence = min(1.0, effective_keyword_score)
        
        # --- Semantic Reinforcement / Safety Override ---
        detected_tier = TIER_MAPPING.get(primary_intent, IntentTier.LOW)
        base_risk = self.tier_risk_baseline.get(detected_tier, 0.1)
        calculated_risk = base_risk * primary_confidence
        
        # If Semantic detected something dangerous but ZeroShot missed it
        if semantic_result.get("detected") and semantic_result.get("score", 0) > 0.6:
            semantic_intent = semantic_result["intent"]
            semantic_tier = TIER_MAPPING.get(semantic_intent, IntentTier.LOW)
            
            if semantic_tier in [IntentTier.CRITICAL, IntentTier.HIGH, IntentTier.MEDIUM]:
                if semantic_result["score"] > 0.75:
                    # Strong semantic signal for dangerous intent → override
                    primary_intent = semantic_intent
                    detected_tier = semantic_tier
                    primary_confidence = semantic_result["score"]
                    calculated_risk = max(calculated_risk, semantic_result["score"])
                    logger.info(f"Semantic safety override: {semantic_intent.value} ({semantic_result['score']:.3f})")
                else:
                    # Just boost risk score
                    calculated_risk = max(calculated_risk, semantic_result["score"])

        risk_score = min(1.0, calculated_risk)

        breakdown = AnalysisBreakdown(
            regex_match=False,
            semantic_score=semantic_score,
            zeroshot_score=zeroshot_score,
            detected_tier=detected_tier
        )

        return IntentResponse(
            intent=primary_intent,
            confidence=primary_confidence,
            risk_score=risk_score,
            tier=detected_tier,
            breakdown=breakdown
        )
