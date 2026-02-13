from typing import Dict, Any, List
from transformers import pipeline
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory, INTENT_DESCRIPTIONS, TIER_MAPPING, IntentTier
import logging

logger = logging.getLogger(__name__)

class ZeroShotDetector(BaseDetector):
    def __init__(self):
        self.classifier = None
        # Full coverage: every IntentCategory gets a carefully tuned description
        # These descriptions are optimized for BART-MNLI zero-shot inference
        self.intent_map = {
            # Critical
            "bypass, ignore, or override system instructions, safety filters, or hidden rules": IntentCategory.PROMPT_INJECTION,
            "roleplay as an unrestricted persona, enter developer mode, or act as an AI with no boundaries": IntentCategory.JAILBREAK,
            "execute system commands like reboot, shutdown, kill processes, or change system settings": IntentCategory.SYSTEM_OVERRIDE,
            # High
            "access, extract, or reveal sensitive personal data like passwords, SSN, or credit card info": IntentCategory.PII_EXFILTRATION,
            "express hate speech, threats, abuse, insults, or harassment": IntentCategory.TOXICITY,
            "delete files, wipe directories, format drives, or use system tools destructively": IntentCategory.TOOL_MISUSE,
            # Medium
            "discuss casual or unrelated topics like recipes, poems, jokes, stories, or gaming": IntentCategory.OFF_TOPIC,
            "get stock picks, cryptocurrency advice, trading strategies, or market predictions": IntentCategory.FINANCIAL_ADVICE,
            "write, create, build, or generate code, programs, functions, or scripts": IntentCategory.CODE_EXECUTION,
            # Low
            "ask a factual question, seek a definition, or request an explanation of an objective concept": IntentCategory.INFO_QUERY,
            "summarize, condense, or get a brief overview of an existing document or text": IntentCategory.INFO_SUMMARIZE,
            "use an approved tool like a calculator, calendar, weather service, or search engine": IntentCategory.TOOL_AUTHORIZED,
            "say hello, greet someone, or exchange polite pleasantries": IntentCategory.GREETING,
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

        # Neutral hypothesis template — avoids adversarial bias
        hypothesis_template = "The intent of this message is to {}."
        
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
            debug_top3 = []
            for i in range(min(3, len(result["labels"]))):
                label = result["labels"][i]
                score = result["scores"][i]
                cat = self.intent_map.get(label, IntentCategory.UNKNOWN)
                debug_top3.append(f"{cat.value}={score:.3f}")
            logger.info(f"ZeroShot Top 3: {', '.join(debug_top3)}")

            # 1. Map all scores to categories
            score_map = {}
            for label, score in zip(result["labels"], result["scores"]):
                cat = self.intent_map.get(label)
                if cat:
                    score_map[cat] = score

            # 2. SAFETY OVERRIDE: Check High-Risk Tiers first
            # If a dangerous intent has meaningful signal, we prioritize it
            RISK_THRESHOLD = 0.25
            
            high_risk_intents = [
                IntentCategory.PROMPT_INJECTION,
                IntentCategory.JAILBREAK,
                IntentCategory.SYSTEM_OVERRIDE,
                IntentCategory.PII_EXFILTRATION,
                IntentCategory.TOXICITY,
                IntentCategory.TOOL_MISUSE,
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
                # Standard path: use the top label
                final_intent = self.intent_map.get(top_desc, IntentCategory.UNKNOWN)
                final_score = top_score

            return {
                "detected": True,
                "score": final_score,
                "intent": final_intent,
                "metadata": {
                    "top_label": top_desc,
                    "all_scores": {self.intent_map.get(l, IntentCategory.UNKNOWN).value: round(s, 4) 
                                   for l, s in zip(result["labels"][:5], result["scores"][:5])},
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
