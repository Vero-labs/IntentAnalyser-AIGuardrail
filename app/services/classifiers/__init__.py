"""
Base classifier interface for the tri-axis pipeline.

Each classifier is responsible for ONE axis only.
Detection produces structured facts. Never policy decisions.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseClassifier(ABC):
    @abstractmethod
    def classify(self, text: str) -> Dict[str, Any]:
        """
        Classify text along a single axis.

        Must return a dict with at least:
          - result:     The primary classification value (enum member)
          - confidence: float 0.0–1.0
          - all_scores: Dict[str, float] — scores for all candidates
          - metadata:   Dict — detector-specific debug info
        """
        pass

    async def load(self):
        """Optional async initialization (model loading etc.)."""
        pass
