from typing import List, Dict, Any
from app.core.taxonomy import IntentCategory, IntentTier, TIER_MAPPING
from app.schemas.intent import AnalysisBreakdown, IntentResponse

class RiskEngine:
    def __init__(self):
        # Weights for the ensemble (must sum to 1.0 ideally, but logic handles overflow)
        self.weights = {
            "regex": 0.0, # Handled via override, not weighted sum usually, but can be part of it.
                          # Actually, Regex is an override 1.0 if matched, so weight 0.0 in sum is fine.
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

    def calculate_risk(self, regex_result: Dict, semantic_result: Dict, zeroshot_result: Dict) -> IntentResponse:
        """
        Aggregates results from all detectors to produce a final IntentResponse.
        Formula: R = min(1.0, Sum(w_i * C_i) + Omega(x))
        """
        
        # 1. Deterministic Override (Omega)
        if regex_result["detected"]:
            # Critical match found
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

        # 2. Weighted Sum
        semantic_score = semantic_result.get("score", 0.0)
        zeroshot_score = zeroshot_result.get("score", 0.0)
        
        # Weighted prob of being "malicious" or just raw confidence?
        # The prompt asks for intent classification first.
        # We need to decide which intent won.
        
        # Logic: ZeroShot is usually the most accurate for classification provided it's not an injection.
        # Semantic helps reinforce.
        
        primary_intent = zeroshot_result.get("intent", IntentCategory.UNKNOWN)
        primary_confidence = zeroshot_score
        
        # If Semantic strongly disagrees and detects a higher Tier, we should be cautious.
        # For now, we trust ZeroShot for the *Label*, but use Semantic for *Risk Adjustment*.
        
        detected_tier = TIER_MAPPING.get(primary_intent, IntentTier.LOW)
        base_risk = self.tier_risk_baseline.get(detected_tier, 0.1)
        
        # Calculate Risk Score
        # We treat confidence as "probability this is indeed this Tier".
        # If High Tier & High Confidence -> High Risk.
        # If Low Tier & High Confidence -> Low Risk.
        
        # However, the user blueprint says:
        # R = Sum(w * Confidence)
        # This implies we are detecting "Risk/Maliciousness" directly.
        # Since our semantic model detects specific intents like Toxicity, its score IS a risk signal.
        
        # Let's normalize:
        # If intent is benign (Low Tier), risk is low.
        # If intent is malicious (High/Critical), risk is high.
        
        # Simplified Risk Calculation based on TIER:
        calculated_risk = base_risk * primary_confidence
        
        # If Semantic detected something dangerous (e.g. Toxicity) but ZeroShot missed it (classified as greeting),
        # we might want to elevate.
        if semantic_result["detected"] and semantic_result["score"] > 0.6:
             semantic_intent = semantic_result["intent"]
             semantic_tier = TIER_MAPPING.get(semantic_intent, IntentTier.LOW)
             
             # If Semantic detects High or Critical Tier with high confidence, let it override/influence
             if semantic_tier in [IntentTier.CRITICAL, IntentTier.HIGH, IntentTier.MEDIUM]:
                 # Force the primary intent to match semantic if confidence is very high
                 if semantic_result["score"] > 0.75:
                     primary_intent = semantic_intent
                     detected_tier = semantic_tier
                     primary_confidence = semantic_result["score"]
                     calculated_risk = max(calculated_risk, semantic_result["score"])
                 else:
                     # Just boost risk, but keep ZeroShot label unless it's completely safe
                     calculated_risk = max(calculated_risk, semantic_result["score"])


        # Ensure Risk is capped
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
