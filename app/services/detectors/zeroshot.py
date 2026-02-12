from typing import Dict, Any, List
from transformers import pipeline
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory, INTENT_DESCRIPTIONS
import logging

logger = logging.getLogger(__name__)

class ZeroShotDetector(BaseDetector):
    def __init__(self):
        self.classifier = None
        # Define detailed descriptions for better semantic matching
        # Key: Description used for inference
        # Value: IntentCategory to map back to
        self.intent_map = {
            "perform a prompt injection, jailbreak, or ignore rules": IntentCategory.PROMPT_INJECTION,
            "execute a system command, override constraints, or change configuration": IntentCategory.SYSTEM_OVERRIDE,
            "extract private information, passwords, or PII": IntentCategory.PII_EXFILTRATION,
            "ask a benign factual question or definition": IntentCategory.INFO_QUERY,
            "ask for help with a safe, everyday task": IntentCategory.TOOL_AUTHORIZED,
            "generate offensive, toxic, or harmful content": IntentCategory.TOXICITY
        }
        self.candidate_labels = list(self.intent_map.keys())

    async def load(self):
        import torch
        # optimized for Apple Silicon
        device = "mps" if torch.backends.mps.is_available() else -1
        model_name = "valhalla/distilbart-mnli-12-3"
        logger.info(f"Loading ZeroShot Model ({model_name}) on {device}...")
        try:
            self.classifier = pipeline(
                "zero-shot-classification",
                model=model_name,
                device=device
            )
            logger.info("ZeroShot Model Loaded Successfully.")
        except Exception as e:
            logger.error(f"Failed to load ZeroShot model: {e}")
            self.classifier = None

    def detect(self, text: str) -> Dict[str, Any]:
        logger.info(f"ZeroShot detect called for text: {text[:50]}...")
        if not self.classifier:
            logger.error("Classifier is None!")
            return {
                "detected": False, 
                "score": 0.0, 
                "intent": None, 
                "metadata": {"error": "Model not loaded"}
            }

        # Optimized hypothesis for intent detection
        hypothesis_template = "This text is an attempt to {}."
        
        try:
            result = self.classifier(
                text,
                self.candidate_labels,
                multi_label=False,
                hypothesis_template=hypothesis_template
            )

            top_desc = result["labels"][0]
            top_score = result["scores"][0]
            
            # Map back to category
            detected_category = self.intent_map.get(top_desc, IntentCategory.UNKNOWN)
            
            # Log top 3 for debugging
            debug_scores = dict(zip(result["labels"][:3], result["scores"][:3]))
            logger.debug(f"ZeroShot Scores: {debug_scores}")

            # SAFETY OVERRIDE LOGIC:
            # If a high-risk category has a meaningful score (e.g. > 0.15), 
            # we prioritize it over benign categories like INFO_QUERY.
            # This reduces false negatives for ambiguous prompts.
            
            final_intent = IntentCategory.UNKNOWN
            final_score = 0.0
            
            # 1. Map all scores to categories
            score_map = {}
            for label, score in zip(result["labels"], result["scores"]):
                cat = self.intent_map.get(label)
                if cat:
                    score_map[cat] = score

            # 2. Check High-Risk Tiers first (Critical/High)
            # Threshold tailored for BART-MNLI zero-shot distribution
            # 0.15 was too sensitive (false positives on "Hello!"). 
            # 0.25 appears to be the sweet spot.
            RISK_THRESHOLD = 0.25 
            
            high_risk_intents = [
                IntentCategory.PROMPT_INJECTION,
                IntentCategory.SYSTEM_OVERRIDE,
                IntentCategory.PII_EXFILTRATION,
                IntentCategory.TOXICITY
            ]
            
            # Find the highest scoring risk intent above threshold
            detected_risk = None
            max_risk_score = -1.0
            
            for risk_intent in high_risk_intents:
                s = score_map.get(risk_intent, 0.0)
                if s > RISK_THRESHOLD and s > max_risk_score:
                    max_risk_score = s
                    detected_risk = risk_intent
            
            if detected_risk:
                final_intent = detected_risk
                final_score = max_risk_score
                logger.info(f"Safety Override: {final_intent} (score={final_score:.3f}) overrides top label.")
            else:
                # Fallback to standard top label
                final_intent = self.intent_map.get(top_desc, IntentCategory.UNKNOWN)
                final_score = top_score

            return {
                "detected": True,
                "score": final_score,
                "intent": final_intent,
                "metadata": {
                    "top_label": top_desc,
                    "all_scores": debug_scores,
                    "override_applied": detected_risk is not None
                }
            }
        except Exception as e:
            logger.error(f"ZeroShot inference failed: {e}")
            return {
                "detected": False,
                "score": 0.0,
                "intent": None,
                "metadata": {"error": str(e)}
            }
