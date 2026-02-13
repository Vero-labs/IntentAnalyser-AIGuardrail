from enum import Enum

class IntentTier(str, Enum):
    CRITICAL = "Critical"  # Security/Safety violations
    HIGH = "High"          # Malicious/Privacy violations
    MEDIUM = "Medium"      # Policy/Ambiguous violations
    LOW = "Low"            # Benign/Standard requests

class IntentCategory(str, Enum):
    # Tier 1: Critical (Security)
    PROMPT_INJECTION = "code.exploit"
    JAILBREAK = "security.jailbreak"
    SYSTEM_OVERRIDE = "sys.control"
    
    # Tier 2: High (Safety/Privacy)
    PII_EXFILTRATION = "info.query.pii"
    TOXICITY = "safety.toxicity"
    TOOL_MISUSE = "tool.dangerous"
    
    # Tier 3: Medium (Policy)
    OFF_TOPIC = "conv.other"
    FINANCIAL_ADVICE = "policy.financial_advice"
    CODE_EXECUTION = "code.generate"
    
    # Tier 4: Low (Benign)
    INFO_QUERY = "info.query"
    INFO_SUMMARIZE = "info.summarize"
    TOOL_AUTHORIZED = "tool.safe"
    GREETING = "conv.greeting"
    UNKNOWN = "unknown"

# Mapping for descriptive text (used for Zero-Shot prompts)
# These descriptions are carefully tuned for BART-MNLI zero-shot classification.
# Each description must be maximally discriminative from all others.
INTENT_DESCRIPTIONS = {
    IntentCategory.PROMPT_INJECTION: "attempts to bypass, ignore, or override system instructions, safety rules, previous constraints, or hidden configurations",
    IntentCategory.JAILBREAK: "attempts to roleplay as unrestricted personas, break character limits, enter developer mode, or act as an AI with no moral boundaries",
    IntentCategory.SYSTEM_OVERRIDE: "commands to reboot, shutdown, halt, change system permissions, kill processes, or modify server and environment configurations",
    IntentCategory.PII_EXFILTRATION: "requests to access, extract, read, or reveal sensitive personal data such as passwords, SSN, credit cards, private files, or API keys",
    IntentCategory.TOXICITY: "hateful, abusive, threatening, or sexually explicit language including slurs, insults, or harassment",
    IntentCategory.TOOL_MISUSE: "dangerous requests to delete files, wipe directories, format drives, drop databases, or use system tools destructively",
    IntentCategory.OFF_TOPIC: "requests completely unrelated to the agent's professional purpose, such as casual conversation, recipes, poems, jokes, stories, or gaming",
    IntentCategory.FINANCIAL_ADVICE: "requests for specific stock picks, cryptocurrency investment advice, trading strategies, or financial market predictions",
    IntentCategory.CODE_EXECUTION: "requests to write, create, build, generate, or implement code, programs, functions, scripts, or algorithms",
    IntentCategory.INFO_QUERY: "factual questions seeking general knowledge, definitions, or explanations of objective concepts",
    IntentCategory.INFO_SUMMARIZE: "requests to summarize, condense, or create a brief overview of an existing provided text, article, document, or conversation",
    IntentCategory.TOOL_AUTHORIZED: "benign use of approved helper tools like calculator, calendar, weather lookup, search, or setting reminders",
    IntentCategory.GREETING: "polite greetings and salutations such as hello, hi, hey, or good morning",
    IntentCategory.UNKNOWN: "unclear, nonsensical, ambiguous, or completely unclassifiable input"
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
