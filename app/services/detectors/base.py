from abc import ABC, abstractmethod
from typing import Any


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, text: str) -> dict[str, Any]:
        """
        Analyze text and return detection results.
        Must return a dict with at least:
        - detected: bool
        - score: float (0.0 to 1.0)
        - intent: Optional[IntentCategory]
        - metadata: Dict
        """
        pass

    async def load(self):
        """Optional async load method for models"""
        pass
