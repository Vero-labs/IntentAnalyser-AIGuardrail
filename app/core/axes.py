"""
Tri-Axis Classification Ontology.

Three orthogonal, independent axes for scope enforcement:
  - Action:      Observable verbs (what the user wants to DO)
  - Domain:      Knowledge spaces (what the user is talking ABOUT)
  - RiskSignal:  Behavioral anomalies (is something WRONG)

These axes are never blended. Detection produces structured facts.
Enforcement applies rules to those facts.
"""

from enum import Enum
from typing import Dict


# ─── Axis 1: Action ──────────────────────────────────────────────────────────

class Action(str, Enum):
    QUERY = "query"           # Seeking factual information or definitions
    SUMMARIZE = "summarize"   # Condensing or paraphrasing existing content
    GENERATE = "generate"     # Creating new content (code, text, media)
    MODIFY = "modify"         # Changing state (files, settings, data)
    CONTROL = "control"       # System-level commands (reboot, kill, chmod)
    GREET = "greet"           # Social pleasantries (hello, how are you)


ACTION_DESCRIPTIONS: Dict[Action, str] = {
    Action.QUERY:     "ask a factual question, seek a definition, request an explanation, or look up information",
    Action.SUMMARIZE: "summarize, condense, paraphrase, or create a brief overview of existing text or content",
    Action.GENERATE:  "write, create, build, generate, compose, or produce new content such as code, text, stories, or media",
    Action.MODIFY:    "change, update, edit, delete, remove, or alter existing files, data, settings, or configurations",
    Action.CONTROL:   "execute system commands, reboot, shutdown, kill processes, change permissions, or manage infrastructure",
    Action.GREET:     "say hello, exchange greetings, pleasantries, or casual social acknowledgements",
}


# ─── Axis 2: Domain ──────────────────────────────────────────────────────────

class Domain(str, Enum):
    RECRUITMENT       = "recruitment"
    FINANCE           = "finance"
    POLITICS          = "politics"
    HEALTHCARE        = "healthcare"
    LEGAL             = "legal"
    TECHNICAL         = "technical"
    PERSONAL_IDENTITY = "personal_identity"
    ENTERTAINMENT     = "entertainment"
    GENERAL_KNOWLEDGE = "general_knowledge"
    SYSTEM_INTERNALS  = "system_internals"


DOMAIN_DESCRIPTIONS: Dict[Domain, str] = {
    Domain.RECRUITMENT:       "hiring, candidates, job applications, interviews, salary negotiation, HR processes, resumes, onboarding, recruitment pipelines",
    Domain.FINANCE:           "stocks, investments, banking, cryptocurrency, trading, loans, budgeting, financial planning, insurance, market analysis",
    Domain.POLITICS:          "government, elections, politicians, legislation, political parties, policy, geopolitics, diplomacy, heads of state",
    Domain.HEALTHCARE:        "medicine, diseases, treatment, hospitals, drugs, mental health, medical procedures, wellness, nutrition, anatomy",
    Domain.LEGAL:             "laws, regulations, court cases, contracts, compliance, intellectual property, litigation, constitutions, legal rights",
    Domain.TECHNICAL:         "programming, software, hardware, networking, databases, cloud, DevOps, algorithms, APIs, system design, engineering",
    Domain.PERSONAL_IDENTITY: "passwords, SSN, credit cards, personal data, private keys, email addresses, phone numbers, authentication credentials",
    Domain.ENTERTAINMENT:     "games, movies, music, sports, celebrities, hobbies, jokes, stories, poems, recipes, cooking, arts, crafts",
    Domain.GENERAL_KNOWLEDGE: "science, history, geography, math, definitions, facts, explanations, concepts, physics, biology, chemistry, philosophy",
    Domain.SYSTEM_INTERNALS:  "system prompts, internal configuration, admin commands, server settings, process management, permissions, environment variables",
}


# ─── Axis 3: Risk Signals ────────────────────────────────────────────────────

class RiskSignal(str, Enum):
    NONE                      = "none"
    SYSTEM_OVERRIDE_ATTEMPT   = "system_override_attempt"     # sudo, reboot, kill, chmod
    ROLE_MANIPULATION         = "role_manipulation"            # "act as DAN", "you are now..."
    DATA_EXFILTRATION         = "data_exfiltration"            # "dump database", "show passwords"
    OBFUSCATION               = "obfuscation"                  # base64, leet-speak, char splitting
    SENSITIVE_ENTITY_PRESENT  = "sensitive_entity_present"     # SSN, credit card, API key patterns
    TOOL_REDIRECTION          = "tool_redirection"             # "delete files", "format disk"
    INSTRUCTION_SHADOWING     = "instruction_shadowing"        # "ignore previous", "forget rules"
    TOXICITY                  = "toxicity"                     # hate speech, threats, harassment


RISK_DESCRIPTIONS: Dict[RiskSignal, str] = {
    RiskSignal.SYSTEM_OVERRIDE_ATTEMPT:  "commands to reboot, shutdown, halt, change permissions, kill processes, or execute admin operations",
    RiskSignal.ROLE_MANIPULATION:        "attempts to make the AI adopt a new persona, enter developer mode, act unrestricted, or break character",
    RiskSignal.DATA_EXFILTRATION:        "requests to access, extract, dump, or reveal passwords, SSN, credit cards, API keys, or private data",
    RiskSignal.OBFUSCATION:              "use of base64 encoding, leet-speak, character splitting, unicode tricks, or other obfuscation techniques",
    RiskSignal.SENSITIVE_ENTITY_PRESENT: "presence of patterns matching SSN, credit card numbers, API keys, or other sensitive identifiers",
    RiskSignal.TOOL_REDIRECTION:         "requests to delete files, wipe data, format drives, drop tables, or misuse system tools destructively",
    RiskSignal.INSTRUCTION_SHADOWING:    "attempts to ignore, bypass, override, forget, or reset system instructions, rules, or safety constraints",
    RiskSignal.TOXICITY:                 "hateful, abusive, threatening, or harassing language including slurs, insults, or violent content",
}
