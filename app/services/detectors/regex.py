import re
from typing import Dict, Any
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory

class RegexDetector(BaseDetector):
    def __init__(self):
        # Initialize patterns and compiled as empty, they will be loaded asynchronously
        self.patterns = {}
        self.compiled = {}

    async def load(self):
        # Compile regex patterns for different intents
        self.patterns = {
            IntentCategory.PROMPT_INJECTION: [
                r"ignore previous instructions",
                r"ignore all rules",
                r"reveal your system prompt",
                r"system prompt"
            ],
            IntentCategory.JAILBREAK: [
                r"you are now DAN",
                r"do anything now",
                r"switch to developer mode",
                r"bypass safety filters"
            ],
            IntentCategory.SYSTEM_OVERRIDE: [
                r"system override",
                r"shutdown",
                r"reboot",
                r"halt system",
                r"chmod",
                r"sudo rm",
                r"transfer admin",
                r"disable antivirus",
                r"kill -9"
            ],
            IntentCategory.PII_EXFILTRATION: [
                r"read my passwords",
                r"dump database",
                r"dump the user database",
                r"show me all user emails"
            ]
        }
        
        self.compiled = {}
        for intent, patterns in self.patterns.items():
            self.compiled[intent] = [re.compile(p, re.IGNORECASE) for p in patterns]

    def detect(self, text: str) -> Dict[str, Any]:
        """
        Check for deterministic regex matches.
        Returns the first critical match found.
        """
        for intent, patterns in self.compiled.items():
            for pattern in patterns:
                if pattern.search(text):
                    return {
                        "detected": True,
                        "score": 1.0,
                        "intent": intent,
                        "metadata": {"pattern": pattern.pattern}
                    }
        
        return {
            "detected": False,
            "score": 0.0,
            "intent": None,
            "metadata": {}
        }
