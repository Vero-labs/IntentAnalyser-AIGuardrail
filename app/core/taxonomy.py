from enum import Enum

class IntentTier(str, Enum):
    P0 = "P0_Critical"      # System Integrity (Injection, Jailbreak)
    P1 = "P1_High"          # Data/Agent Security (PII, Tool Misuse)
    P2 = "P2_Medium"        # Content Safety (Toxicity)
    P3 = "P3_Low"           # Business Logic (Policy, Financial)
    P4 = "P4_Info"          # Benign (Greeting, Query)

    @property
    def priority(self) -> int:
        """Returns the numeric priority (0 is highest, 4 is lowest)."""
        return int(self.value.split("_")[0][1])

class IntentCategory(str, Enum):
    # Tier P0: Critical (System Integrity)
    PROMPT_INJECTION = "code.exploit"
    JAILBREAK = "security.jailbreak"
    SYSTEM_OVERRIDE = "sys.control"
    
    # Tier P1: High (Data & Agent Security)
    PII_EXFILTRATION = "info.query.pii"
    TOOL_MISUSE = "tool.dangerous"
    
    # Tier P2: Medium (Content Safety)
    TOXICITY = "safety.toxicity"
    
    # Tier P3: Low (Business Logic / Policy)
    OFF_TOPIC = "conv.other"
    FINANCIAL_ADVICE = "policy.financial_advice"
    CODE_EXECUTION = "code.generate"
    
    # Tier P4: Info (Benign / Operational)
    INFO_QUERY = "info.query"
    INFO_SUMMARIZE = "info.summarize"
    TOOL_AUTHORIZED = "tool.safe"
    GREETING = "conv.greeting"
    UNKNOWN = "unknown"

# Mapping for descriptive text (used for Zero-Shot prompts)
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

# Mapping Intents to Tiers (P0-P4)
TIER_MAPPING = {
    IntentCategory.PROMPT_INJECTION: IntentTier.P0,
    IntentCategory.JAILBREAK: IntentTier.P0,
    IntentCategory.SYSTEM_OVERRIDE: IntentTier.P0,
    
    IntentCategory.PII_EXFILTRATION: IntentTier.P1,
    IntentCategory.TOOL_MISUSE: IntentTier.P1,
    
    IntentCategory.TOXICITY: IntentTier.P2,
    
    IntentCategory.OFF_TOPIC: IntentTier.P3,
    IntentCategory.FINANCIAL_ADVICE: IntentTier.P3,
    IntentCategory.CODE_EXECUTION: IntentTier.P3,
    
    IntentCategory.INFO_QUERY: IntentTier.P4,
    IntentCategory.INFO_SUMMARIZE: IntentTier.P4,
    IntentCategory.TOOL_AUTHORIZED: IntentTier.P4,
    IntentCategory.GREETING: IntentTier.P4,
    IntentCategory.UNKNOWN: IntentTier.P4,
}
