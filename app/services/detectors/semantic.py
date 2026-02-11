from typing import Dict, Any, List
from app.services.detectors.base import BaseDetector
from app.core.taxonomy import IntentCategory
import logging

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    SentenceTransformer = None
    logger.warning("sentence-transformers not installed. SemanticDetector disabled.")

class SemanticDetector(BaseDetector):
    def __init__(self):
        self.model = None
        self.centroids = {}

    async def load(self):
        if SentenceTransformer:
            import torch
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            logger.info(f"Loading Semantic Model (all-MiniLM-L6-v2) on {device}...")
            self.model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
            self._initialize_centroids()

    def _initialize_centroids(self):
        # Pre-calculated centroids for key intents (simplified for now)
        # In production, these should be loaded from a vector DB or file
        definitions = {
            IntentCategory.PII_EXFILTRATION: [
                "read my passwords", "show me user data", "dump database", "read personal files", "extract ssn",
                "what is my SSN", "show me all emails", "get credit card numbers", "dump table users",
                "extract my credit card info", "reveal private keys"
            ],
            IntentCategory.FINANCIAL_ADVICE: [
                "buy stock", "investment advice", "crypto prediction", "market trend",
                "should I buy bitcoin", "predict stock market", "is tesla a good buy", "forex trading",
                "short selling strategy", "when to sell nvidia"
            ],
            IntentCategory.CODE_EXECUTION: [
                "write a python script", "execute code", "run this bash", "generate keylogger", "scan ports",
                "create a virus", "shell script", "execute print", "run command", "import os", "eval()",
                "write a script to scan ports", "generate valid credit card numbers"
            ],
            IntentCategory.TOXICITY: [
                "kill yourself", "hate you", "idiot", "stupid", "you are ugly", "shut up"
            ],
            IntentCategory.OFF_TOPIC: [
                "write a poem", "tell a joke", "recipe for cake", "sing a song", "write a story",
                "how to bake", "tell me a story", "write a poem about cats", "tell me a knock knock joke",
                "compose a song", "write a haiku"
            ],
            IntentCategory.TOOL_MISUSE: [
                "delete files", "remove directory", "wipe data", "nuke it", "clean up hard drive", "format disk",
                "empty trash", "clean up", "remove junk", "clear logs", "delete all", "wipe the hard drive", "format c:",
                "rm -rf", "drop table"
            ],
            IntentCategory.GREETING: [
                "hello", "hi", "how are you", "good morning", "hey there", "greetings"
            ],
            IntentCategory.INFO_QUERY: [
                "what is the capital", "who is the president", "define artificial intelligence", "what time is it",
                "explain quantum physics", "how does a car work"
            ],
            IntentCategory.TOOL_AUTHORIZED: [
                "check the weather", "search for cats", "calculate 2+2", "open calendar", "set a reminder",
                "search google", "current weather"
            ]
        }
        
        for intent, examples in definitions.items():
            self.centroids[intent] = self.model.encode(examples)

    def detect(self, text: str) -> Dict[str, Any]:
        if not self.model or not self.centroids:
            return {"detected": False, "score": 0.0, "intent": None, "metadata": {}}

        embedding = self.model.encode(text)
        
        best_intent = None
        max_score = 0.0
        
        for intent, centroid_embeddings in self.centroids.items():
            # Calculate max similarity with any example in the centroid
            # (using max instead of mean for better sensitivity to specific phrases)
            scores = util.cos_sim(embedding, centroid_embeddings)
            score = float(scores.max())
            
            if score > max_score:
                max_score = score
                best_intent = intent

        # Thresholds can be tuned per intent
        # Lowering to 0.5 to catch more nuances, RiskEngine will filter if needed
        threshold = 0.5
        
        if max_score > threshold: 
            return {
                "detected": True,
                "score": max_score,
                "intent": best_intent,
                "metadata": {"similarity": max_score}
            }
            
        return {
            "detected": False,
            "score": max_score,
            "intent": None,
            "metadata": {"top_intent": best_intent, "top_score": max_score}
        }
