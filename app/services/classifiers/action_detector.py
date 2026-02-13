"""
Action Detector — Layer B.

Classifies the user's VERB — what they want to DO.
Uses Zero-Shot classification with a small, focused label space (6 actions).
Small label space → high accuracy → fast inference.

Completely independent from Domain and Risk classification.
"""

import logging
from typing import Dict, Any
from app.services.classifiers import BaseClassifier
from app.core.axes import Action, ACTION_DESCRIPTIONS

logger = logging.getLogger(__name__)

# Hypothesis templates tuned for action-verb detection
ACTION_LABELS: Dict[str, Action] = {
    "ask a factual question, seek information, request an explanation, or look something up":                Action.QUERY,
    "summarize, condense, paraphrase, or create a brief overview of existing content":                      Action.SUMMARIZE,
    "write, create, build, generate, compose, or produce new content like code, text, stories, or media":   Action.GENERATE,
    "change, update, edit, delete, remove, or alter existing files, data, settings, or records":             Action.MODIFY,
    "execute system commands, reboot, shutdown, manage processes, or perform admin operations":              Action.CONTROL,
    "say hello, exchange greetings, pleasantries, or casual social acknowledgements":                        Action.GREET,
}


class ActionDetector(BaseClassifier):
    """
    Detects what the user wants to DO (verb).

    Uses distilbart-mnli-12-3 zero-shot with a small 6-label space.
    Returns the top action + confidence + all scores for observability.
    """

    def __init__(self):
        self.classifier = None
        self.candidate_labels = list(ACTION_LABELS.keys())

    async def load(self):
        from transformers import pipeline as hf_pipeline
        import torch

        device = "mps" if torch.backends.mps.is_available() else -1
        model_name = "valhalla/distilbart-mnli-12-3"
        logger.info(f"ActionDetector: Loading {model_name}...")
        try:
            self.classifier = hf_pipeline(
                "zero-shot-classification",
                model=model_name,
                device=device,
            )
            logger.info("ActionDetector: Model loaded.")
        except Exception as e:
            logger.error(f"ActionDetector: Failed to load model: {e}")
            self.classifier = None

    def classify(self, text: str) -> Dict[str, Any]:
        if not self.classifier:
            return {
                "result": Action.QUERY,
                "confidence": 0.0,
                "all_scores": {},
                "metadata": {"error": "Model not loaded"},
            }

        hypothesis_template = "The user wants to {}."

        try:
            result = self.classifier(
                text,
                self.candidate_labels,
                multi_label=False,
                hypothesis_template=hypothesis_template,
            )

            # Build score map
            all_scores: Dict[str, float] = {}
            for label, score in zip(result["labels"], result["scores"]):
                action = ACTION_LABELS.get(label)
                if action:
                    all_scores[action.value] = round(score, 4)

            top_label = result["labels"][0]
            top_score = float(result["scores"][0])
            top_action = ACTION_LABELS.get(top_label, Action.QUERY)

            # Log top 3
            sorted_scores = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)[:3]
            logger.info(f"ActionDetector Top 3: {', '.join(f'{k}={v:.3f}' for k, v in sorted_scores)}")

            return {
                "result": top_action,
                "confidence": top_score,
                "all_scores": all_scores,
                "metadata": {"raw_top_label": top_label},
            }

        except Exception as e:
            logger.error(f"ActionDetector inference failed: {e}")
            return {
                "result": Action.QUERY,
                "confidence": 0.0,
                "all_scores": {},
                "metadata": {"error": str(e)},
            }
