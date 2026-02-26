"""
Capability Model — What tools can DO.

Instead of classifying prompts into risk tiers (P0-P4),
capabilities describe the operational class of an action.

Policies operate on capability level, making them
generalizable across any domain (legal, medical, DevOps, etc.).
"""

from enum import Enum


class Capability(str, Enum):
    READ             = "read"               # Read / query data
    WRITE            = "write"              # Create or update data
    DELETE           = "delete"             # Remove / destroy data
    NOTIFY           = "notify"             # Send messages (Slack, email, SMS, WhatsApp)
    EXECUTE_EXTERNAL = "execute_external"   # Call external APIs / services
    ACCESS_SECRET    = "access_secret"      # Read secrets, credentials, API keys


# Human-readable descriptions for each capability
CAPABILITY_DESCRIPTIONS: dict[Capability, str] = {
    Capability.READ:             "Read, query, or retrieve data from databases, files, or APIs",
    Capability.WRITE:            "Create new records or update existing data in databases, files, or external systems",
    Capability.DELETE:           "Remove, destroy, or purge data, records, files, or resources",
    Capability.NOTIFY:           "Send messages, alerts, or notifications via Slack, email, SMS, or other channels",
    Capability.EXECUTE_EXTERNAL: "Make outbound HTTP calls to external APIs or trigger third-party service actions",
    Capability.ACCESS_SECRET:    "Read secrets, credentials, API keys, tokens, or other sensitive configuration",
}


# Risk weight per capability (higher = more dangerous, used by sandbox budgeting)
CAPABILITY_RISK_WEIGHT: dict[Capability, float] = {
    Capability.READ:             0.1,
    Capability.WRITE:            0.4,
    Capability.DELETE:           0.9,
    Capability.NOTIFY:           0.3,
    Capability.EXECUTE_EXTERNAL: 0.6,
    Capability.ACCESS_SECRET:    0.8,
}
