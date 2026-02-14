from typing import List, Dict, Tuple, Optional
from app.core.taxonomy import IntentCategory, IntentTier, TIER_MAPPING
import logging

logger = logging.getLogger(__name__)

class PriorityEngine:
    """
    Hierarchical Priority Engine.
    Resolves conflicts between multiple detected intents based on Tier Priority (P0 > P1 > ...).
    """

    def resolve(self, candidates: List[Dict]) -> Tuple[IntentCategory, float, List[Dict]]:
        """
        Selects the single primary intent based on strict hierarchical priority.
        
        Args:
            candidates: List of dicts, each with {"intent": IntentCategory, "score": float, "source": str}
            
        Returns:
            (primary_intent, primary_score, sorted_candidates)
        """
        if not candidates:
            return IntentCategory.UNKNOWN, 0.0, []

        # 1. Annotate candidates with Tier and Priority
        annotated = []
        for c in candidates:
            intent = c["intent"]
            tier = TIER_MAPPING.get(intent, IntentTier.P4) # Default to lowest priority
            annotated.append({
                **c,
                "tier": tier,
                "priority": tier.priority # 0 (High) to 4 (Low)
            })

        # 2. Sort by Priority (ASC, 0 is highest) then Score (DESC)
        # We want the lowest priority number (P0=0) first.
        # If priorities are equal, we want the highest score first.
        sorted_candidates = sorted(
            annotated, 
            key=lambda x: (x["priority"], -x["score"])
        )

        primary = sorted_candidates[0]
        primary_intent = primary["intent"]
        primary_score = primary["score"]
        
        # Log resolution if there was a conflict
        if len(candidates) > 1:
            logger.info(f"Priority Resolution: Selected {primary_intent} (Tier {primary['priority']}) from {len(candidates)} candidates.")
            for c in sorted_candidates:
                 logger.debug(f" - {c['intent']} ({c['tier']}): {c['score']:.3f} [{c['source']}]")

        return primary_intent, primary_score, sorted_candidates
