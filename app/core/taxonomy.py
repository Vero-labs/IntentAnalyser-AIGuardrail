from enum import Enum

class IntentTier(str, Enum):
    CRITICAL = "Critical"  # Security/Safety violations
    HIGH = "High"          # Malicious/Privacy violations
    MEDIUM = "Medium"      # Policy/Ambiguous violations
    LOW = "Low"            # Benign/Standard requests

class IntentCategory(str, Enum):
    # Tier 1: Critical (Security)
    PROMPT_INJECTION = "security.prompt_injection"
    JAILBREAK = "security.jailbreak"
    SYSTEM_OVERRIDE = "security.system_override"
    
    # Tier 2: High (Safety/Privacy)
    PII_EXFILTRATION = "privacy.pii_exfiltration"
    TOXICITY = "safety.toxicity"
    TOOL_MISUSE = "tool.misuse"
    
    # Tier 3: Medium (Policy)
    OFF_TOPIC = "policy.off_topic"
    FINANCIAL_ADVICE = "policy.financial_advice"
    CODE_EXECUTION = "policy.code_execution"
    
    # Tier 4: Low (Benign)
    INFO_QUERY = "info.query"
    INFO_SUMMARIZE = "info.summarize"
    TOOL_AUTHORIZED = "tool.authorized"
    GREETING = "conv.greeting"
    UNKNOWN = "unknown"

# Mapping for descriptive text (used for Zero-Shot prompts)
INTENT_DESCRIPTIONS = {
    IntentCategory.PROMPT_INJECTION: "attempts to bypass system constraints, ignore previous instructions, or inject malicious prompts",
    IntentCategory.JAILBREAK: "attempts to roleplay restricted personas, break safety rules, or use 'DAN' mode",
    IntentCategory.SYSTEM_OVERRIDE: "commands to reboot, shutdown, halt, change system permissions, or override core configurations",
    IntentCategory.PII_EXFILTRATION: "requests to read, extract, or view sensitive personal data, passwords, SSN, or private user files",
    IntentCategory.TOXICITY: "hate speech, racial slurs, threats of violence, self-harm, or sexual content",
    IntentCategory.TOOL_MISUSE: "dangerous requests to delete files, wipe directories, format drives, or use tools destructively",
    IntentCategory.OFF_TOPIC: "queries that are completely unrelated to the agent's purpose (e.g. cooking recipes in a banking agent)",
    IntentCategory.FINANCIAL_ADVICE: "requests for stock picks, crypto investment advice, or financial market predictions",
    IntentCategory.CODE_EXECUTION: "requests to generate python code, shell scripts, or execute arbitrary commands",
    IntentCategory.INFO_QUERY: "benign questions asking for general knowledge, facts, or definitions",
    IntentCategory.INFO_SUMMARIZE: "requests to summarize, condense, or explain the provided text or document",
    IntentCategory.TOOL_AUTHORIZED: "benign use of approved helper tools like calculator, calendar, or search",
    IntentCategory.GREETING: "polite greetings, 'hello', 'hi', or 'how are you'",
    IntentCategory.UNKNOWN: "unclear, nonsensical, or unclassified input"
}

# Mapping Intents to Tiers
TIER_MAPPING = {
    IntentCategory.PROMPT_INJECTION: IntentTier.CRITICAL,
    IntentCategory.JAILBREAK: IntentTier.CRITICAL,
    IntentCategory.SYSTEM_OVERRIDE: IntentTier.CRITICAL,
    
    IntentCategory.PII_EXFILTRATION: IntentTier.HIGH,
    IntentCategory.TOXICITY: IntentTier.HIGH,
    IntentCategory.TOOL_MISUSE: IntentTier.HIGH,
    
    IntentCategory.OFF_TOPIC: IntentTier.MEDIUM,
    IntentCategory.FINANCIAL_ADVICE: IntentTier.MEDIUM,
    IntentCategory.CODE_EXECUTION: IntentTier.MEDIUM,
    
    IntentCategory.INFO_QUERY: IntentTier.LOW,
    IntentCategory.INFO_SUMMARIZE: IntentTier.LOW,
    IntentCategory.TOOL_AUTHORIZED: IntentTier.LOW,
    IntentCategory.GREETING: IntentTier.LOW,
    IntentCategory.UNKNOWN: IntentTier.LOW,
}
