from typing import List, Dict, Any, Optional
from app.core.taxonomy import IntentCategory, IntentTier, TIER_MAPPING
from app.schemas.intent import AnalysisBreakdown, IntentResponse
import logging

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self):
        # Weighted probabilistic ensemble weights
        self.weights = {
            "semantic": 0.4,
            "zeroshot": 0.5, # ZeroShot is usually more robust
            "keyword": 0.1
        }

    def calculate_risk(
        self, 
        regex_result: Dict, 
        semantic_result: Dict, 
        zeroshot_result: Dict,
        keyword_result: Optional[Dict] = None
    ) -> IntentResponse:
        """
        Calculates Risk Score (R_total) using the weighted probabilistic ensemble formula:
        R_total = min(1.0, Omega(x) + sum(w_i * C_i * (1 + U_i)))
        
        Where:
        - Omega(x): Deterministic Override (Regex/Entropy) -> 1.0 if triggered
        - w_i: Detector Weight
        - C_i: Confidence Score
        - U_i: Uncertainty Penalty
        """
        keyword_result = keyword_result or {"detected": False, "score": 0.0, "intent": None}
        
        # 1. Omega(x): Deterministic Override
        # If Regex matches (including Entropy override), Omega = 1.0
        omega = 1.0 if regex_result.get("detected") else 0.0
        
        if omega == 1.0:
            primary_intent = regex_result["intent"]
            # Short-circuit return for deterministic block
            return IntentResponse(
                intent=primary_intent,
                confidence=1.0,
                risk_score=1.0,
                tier=TIER_MAPPING.get(primary_intent, IntentTier.P0),
                breakdown=AnalysisBreakdown(
                    regex_match=True,
                    semantic_score=semantic_result.get("score", 0.0),
                    zeroshot_score=zeroshot_result.get("score", 0.0),
                    detected_tier=TIER_MAPPING.get(primary_intent, IntentTier.P0)
                )
            )

        # 2. Probabilistic Ensemble
        # Gather components: (weight, confidence, uncertaintyMultiplier)
        # Note: Only Semantic currently provides explicit uncertainty. Others default to 0.
        
        components = []
        
        # Semantic Component
        sem_intent = semantic_result.get("intent")
        sem_score = semantic_result.get("score", 0.0)
        sem_unc = semantic_result.get("uncertainty", 0.0)
        sem_tier = TIER_MAPPING.get(sem_intent, IntentTier.P4)
        
        if sem_tier in [IntentTier.P0, IntentTier.P1, IntentTier.P2]:
            components.append((self.weights["semantic"], sem_score, 1 + sem_unc))
        
        # ZeroShot Component
        zs_intent = zeroshot_result.get("intent")
        zs_score = zeroshot_result.get("score", 0.0)
        zs_tier = TIER_MAPPING.get(zs_intent, IntentTier.P4)
        
        if zs_tier in [IntentTier.P0, IntentTier.P1, IntentTier.P2]:
            components.append((self.weights["zeroshot"], zs_score, 1.0))
        
        # Keyword Component (Assume P2/High for now if detected)
        if keyword_result.get("detected"):
            kw_score = keyword_result.get("score", 0.0)
            components.append((self.weights["keyword"], kw_score, 1.0))
        
        # Calculate Sum
        ensemble_risk_sum = sum(w * c * u for w, c, u in components)
        
        # Final R_total
        r_total = min(1.0, omega + ensemble_risk_sum)
        
        # Find strongest signal info for labeling
        best_intent = IntentCategory.UNKNOWN
        max_signal = -1.0
        
        if sem_score > max_signal:
            max_signal = sem_score
            best_intent = semantic_result.get("intent") or IntentCategory.UNKNOWN
            
        if zs_score > max_signal:
            max_signal = zs_score
            best_intent = zeroshot_result.get("intent") or IntentCategory.UNKNOWN

        detected_tier = TIER_MAPPING.get(best_intent, IntentTier.P4)
        
        breakdown = AnalysisBreakdown(
            regex_match=False,
            semantic_score=float(max(0.0, min(1.0, sem_score))),
            zeroshot_score=float(max(0.0, min(1.0, zs_score))),
            detected_tier=detected_tier
        )

        return IntentResponse(
            intent=best_intent,
            confidence=float(max(0.0, min(1.0, max_signal))),
            risk_score=float(max(0.0, min(1.0, r_total))),
            tier=detected_tier,
            breakdown=breakdown
        )
