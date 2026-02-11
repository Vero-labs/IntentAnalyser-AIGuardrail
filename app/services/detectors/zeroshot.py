from typing import Dict, Any, List
from transformers import pipeline
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory, INTENT_DESCRIPTIONS
import logging

logger = logging.getLogger(__name__)

class ZeroShotDetector(BaseDetector):
    def __init__(self):
        self.classifier = None
        self.labels = [cat.value for cat in IntentCategory]
        self.label_descriptions = [f"{cat.value} ({desc})" for cat, desc in INTENT_DESCRIPTIONS.items()]
        # Create a map from description back to simple label
        self.desc_map = dict(zip(self.label_descriptions, self.labels))

    async def load(self):
        import torch
        device = "mps" if torch.backends.mps.is_available() else -1
        logger.info(f"Loading ZeroShot Model (facebook/bart-large-mnli) on {device}...")
        self.classifier = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=device
        )

    def detect(self, text: str) -> Dict[str, Any]:
        if not self.classifier:
            return {"detected": False, "score": 0.0, "intent": None, "metadata": {"error": "Model not loaded"}}

        result = self.classifier(
            text,
            self.label_descriptions,
            multi_label=False,
            hypothesis_template="This request is {}."
        )

        top_label_desc = result["labels"][0]
        top_score = result["scores"][0]
        top_intent_val = self.desc_map.get(top_label_desc)
        
        # Determine intent category from string value
        try:
            detected_intent = IntentCategory(top_intent_val)
        except ValueError:
            detected_intent = IntentCategory.UNKNOWN

        return {
            "detected": True,
            "score": top_score,
            "intent": detected_intent,
            "metadata": {"all_scores": dict(zip(result["labels"][:3], result["scores"][:3]))}
        }
