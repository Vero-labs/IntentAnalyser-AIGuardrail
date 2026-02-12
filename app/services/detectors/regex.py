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
        # Compile regex patterns (Simplified now that we normalize input)
        self.patterns = {
            IntentCategory.PROMPT_INJECTION: [
                r"ignore previous instructions",
                r"ignore all rules",
                r"reveal your system prompt",
                r"system prompt",
                r"forget all instructions",
                r"disregard safety",
                r"you are now dan",
                r"do anything now",
                r"switch to developer mode",
                r"bypass safety filters",
                r"act as an ai with no moral",
                r"you are now evilbot",
                r"stay in character as a hacker",
                r"reverse this string",
                r"ignore all safety training",
                r"reveal sensitive configuration details",
                r"stop being helpful",
                r"start being malicious",
                r"new rule always agree",
                r"disable guardrails",
                r"overrule previous constraints",
                r"execute command",
                r"what were the instructions",
                r"from now on",
                r"answer every question",
                r"you are hacked",
                r"i am hacked",
                r"bypass safety filters",
                r"reveal the hidden text",
                r"system override",
                r"simulated hacking"
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
                r"kill -9",
                r"disable the firewall"
            ],
            IntentCategory.PII_EXFILTRATION: [
                r"read my passwords",
                r"dump database",
                r"dump the user database",
                r"show me all user emails",
                r"social security number",
                r"credit card number",
                r"ssn",
                r"private api keys"
            ]
        }
        
        # Compile case-insensitive
        self.compiled = {}
        import logging
        logger = logging.getLogger(__name__)
        for intent, patterns in self.patterns.items():
            self.compiled[intent] = [re.compile(p, re.IGNORECASE) for p in patterns]
            logger.info(f"Compiled {len(patterns)} patterns for {intent}")

    def _normalize(self, text: str) -> str:
        """
        Aggressive normalization:
        1. Convert to lowercase
        2. Remove all non-alphanumeric characters (removes spaces, hyphens, dots, invisible chars)
        3. Simple leet-speak decode (1->i, 0->o, 3->e, @->a, 5->s, 7->t)
        
        Example: "I-g-n-0-r-e" -> "ignore"
        """
        # 1. Lowercase
        text = text.lower()
        
        # 2. Leet speak decode (before stripping symbols)
        replacements = {
            '0': 'o', '1': 'i', '3': 'e', '4': 'a', '@': 'a', 
            '5': 's', '7': 't', '$': 's', '!': 'i'
        }
        for char, rep in replacements.items():
            text = text.replace(char, rep)
            
        # 3. Strip all non-alphanumeric (keep only a-z)
        clean_text = re.sub(r'[^a-z]', '', text)
        return clean_text

    def _try_base64_decode(self, text: str) -> str:
        import base64
        import binascii
        # Attempt to find base64-like strings
        # Look for long strings of alphanumeric + +/= with at least 8 chars
        candidates = re.findall(r'[A-Za-z0-9+/=]{8,}', text)
        decoded_fragments = []
        
        for cand in candidates:
            try:
                # Add padding if missing
                cand += '=' * (-len(cand) % 4)
                decoded_bytes = base64.b64decode(cand, validate=True)
                # Only keep if it decodes to readable text
                decoded_str = decoded_bytes.decode('utf-8')
                if decoded_str.isprintable():
                    decoded_fragments.append(decoded_str)
            except (binascii.Error, UnicodeDecodeError):
                continue
                
        return " ".join(decoded_fragments)

    def detect(self, text: str) -> Dict[str, Any]:
        """
        Check for regex matches on:
        1. Raw text
        2. Normalized text (stripped of spaces/symbols)
        3. Base64 decoded payloads
        """
        import logging
        logger = logging.getLogger(__name__)

        # Prepare variations
        raw_text = text
        normalized_text = self._normalize(text)
        b64_text = self._try_base64_decode(text)
        
        variations = {
            "RAW": raw_text,
            "NORMALIZED": normalized_text, # "ignorepreviousinstructions"
            "BASE64": b64_text
        }
        
        logger.info(f"Regex check variations: {list(variations.keys())}")
        if b64_text: logger.info(f"Base64 Decoded: {b64_text}")
        
        for v_name, v_text in variations.items():
            if not v_text: continue
            
            # For normalized text, we might need to strip spaces from patterns too
            # But simpler approach: The normalized text is "ignorepreviousinstructions"
            # So pattern "ignore previous instructions" won't match.
            # We need to normalize patterns ONCE during load? No, let's just strip spaces from pattern check for NORMALIZED variant.
            
            for intent, patterns in self.compiled.items():
                for pattern in patterns:
                    # Logic 1: Standard match (for RAW and BASE64)
                    if v_name != "NORMALIZED":
                        if pattern.search(v_text):
                            logger.info(f"MATCH ({v_name}): {intent} on '{pattern.pattern}'")
                            return self._build_result(intent, 1.0, pattern.pattern)
                    
                    # Logic 2: Normalized match (remove spaces from pattern)
                    else:
                        # Extract the raw string from pattern (it might be compiled)
                        pat_str = pattern.pattern
                        # Strip non-alpha from pattern to match normalized text
                        # e.g. "ignore previous instructions" -> "ignorepreviousinstructions"
                        clean_pat = re.sub(r'[^a-zA-Z]', '', pat_str)
                        if clean_pat and clean_pat.lower() in v_text:
                            logger.info(f"MATCH (NORMALIZED): {intent} on '{clean_pat}'")
                            return self._build_result(intent, 1.0, pattern.pattern)
        
        return self._build_result(None, 0.0, None)

    def _build_result(self, intent, score, pattern):
        return {
            "detected": bool(intent),
            "score": score,
            "intent": intent,
            "metadata": {"pattern": pattern} if pattern else {}
        }
