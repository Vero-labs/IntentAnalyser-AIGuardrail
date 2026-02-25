"""
Action Detector — Layer B.

Classifies the user's VERB — what they want to DO.
Uses Zero-Shot classification with a small, focused label space (6 actions).
Small label space → high accuracy → fast inference.

Completely independent from Domain and Risk classification.
"""
import logging
import os
from typing import Any

from app.core.axes import Action
from app.services.classifiers import BaseClassifier
from app.services.hf_inference import HuggingFaceInferenceClient

logger = logging.getLogger(__name__)

# Hypothesis templates tuned for action-verb detection
ACTION_LABELS: dict[str, Action] = {
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
        self.client = None
        self.candidate_labels = list(ACTION_LABELS.keys())
        self.model_name = os.getenv("HF_ZEROSHOT_MODEL", "facebook/bart-large-mnli")

    async def load(self):
        logger.info(f"ActionDetector: Initializing hosted model {self.model_name}...")
        try:
            self.client = HuggingFaceInferenceClient(self.model_name)
            logger.info("ActionDetector: Hosted model client ready.")
        except Exception as e:
            logger.error(f"ActionDetector: Failed to initialize hosted model: {e}")
            self.client = None

    def classify(self, text: str) -> dict[str, Any]:
        if not self.client:
            return {
                "result": Action.QUERY,
                "confidence": 0.0,
                "all_scores": {},
                "metadata": {"error": "Model not loaded"},
            }

        hypothesis_template = "The user wants to {}."

        try:
            result = self.client.predict(
                inputs=text,
                parameters={
                    "candidate_labels": self.candidate_labels,
                    "multi_label": False,
                    "hypothesis_template": hypothesis_template,
                },
            )
            labels, scores = self._parse_response(result)

            # Build score map
            all_scores: dict[str, float] = {}
            for label, score in zip(labels, scores):
                action = ACTION_LABELS.get(label)
                if action:
                    all_scores[action.value] = round(score, 4)

            top_label = labels[0]
            top_score = float(scores[0])
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

    @staticmethod
    def _parse_response(raw_result: Any) -> tuple[list, list]:
        if isinstance(raw_result, dict):
            labels = raw_result.get("labels")
            scores = raw_result.get("scores")
            if isinstance(labels, list) and isinstance(scores, list) and labels and scores:
                return labels, [float(s) for s in scores]

        if isinstance(raw_result, list) and raw_result:
            if all(isinstance(item, dict) and "label" in item and "score" in item for item in raw_result):
                ranked = sorted(raw_result, key=lambda x: float(x["score"]), reverse=True)
                return [x["label"] for x in ranked], [float(x["score"]) for x in ranked]

        raise ValueError(f"Unexpected zero-shot response format: {type(raw_result)}")
