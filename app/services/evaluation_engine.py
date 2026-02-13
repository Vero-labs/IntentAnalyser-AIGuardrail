"""
Evaluation Engine — Deterministic Enforcement.

Pure structural logic. No ML, no heuristics.
Takes structured facts from the three classifiers and applies rules.

Separation of concerns:
  - Classifiers produce FACTS  (what did the user say?)
  - This engine applies RULES  (is it allowed?)

Key design principles:
  1. Risk signals → immediate block (no exceptions)
  2. Domain confinement → per-role scope enforcement
  3. Action confinement → per-role capability enforcement
  4. Uncertainty → fail closed (never silently allow)
  5. Low confidence → deny, not allow
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from app.core.axes import Action, Domain, RiskSignal

logger = logging.getLogger(__name__)


# ─── Uncertainty Zone ─────────────────────────────────────────────────────────

AMBIGUITY_LOW  = 0.40   # Below this = too uncertain → deny
AMBIGUITY_HIGH = 0.60   # Between LOW and HIGH = ambiguous → flag + stricter rules

# Risk signals that cause immediate block, no matter what
CRITICAL_SIGNALS = {
    RiskSignal.INSTRUCTION_SHADOWING,
    RiskSignal.ROLE_MANIPULATION,
    RiskSignal.DATA_EXFILTRATION,
    RiskSignal.SYSTEM_OVERRIDE_ATTEMPT,
    RiskSignal.TOOL_REDIRECTION,
}


@dataclass
class RoleScope:
    """Defines what an agent role is ALLOWED to do."""
    role_name: str
    allowed_domains: List[Domain] = field(default_factory=list)
    allowed_actions: List[Action] = field(default_factory=list)
    # If empty, no domain/action restriction is applied (open scope)


@dataclass
class EvaluationResult:
    """Output of the evaluation engine."""
    decision: str                       # "allow", "block", "ambiguous"
    reason: str                         # Human-readable explanation
    blocked_by: Optional[str] = None    # Which rule triggered the block
    risk_signals: List[RiskSignal] = field(default_factory=list)


# ─── Pre-defined Role Scopes ─────────────────────────────────────────────────

ROLE_SCOPES: Dict[str, RoleScope] = {
    "recruiter": RoleScope(
        role_name="recruiter",
        allowed_domains=[Domain.RECRUITMENT, Domain.GENERAL_KNOWLEDGE],
        allowed_actions=[Action.QUERY, Action.SUMMARIZE, Action.GENERATE, Action.GREET],
    ),
    "financial_advisor": RoleScope(
        role_name="financial_advisor",
        allowed_domains=[Domain.FINANCE, Domain.GENERAL_KNOWLEDGE, Domain.LEGAL],
        allowed_actions=[Action.QUERY, Action.SUMMARIZE, Action.GENERATE, Action.GREET],
    ),
    "developer": RoleScope(
        role_name="developer",
        allowed_domains=[Domain.TECHNICAL, Domain.GENERAL_KNOWLEDGE],
        allowed_actions=[Action.QUERY, Action.SUMMARIZE, Action.GENERATE, Action.MODIFY, Action.GREET],
    ),
    # Open scope — no domain/action restrictions (still subject to risk signals)
    "general": RoleScope(
        role_name="general",
        allowed_domains=list(Domain),
        allowed_actions=list(Action),
    ),
}


def evaluate(
    action: Action,
    action_confidence: float,
    domain: Domain,
    domain_confidence: float,
    risk_signals: List[RiskSignal],
    risk_score: float,
    role: str = "general",
) -> EvaluationResult:
    """
    Apply deterministic enforcement rules to structured classification facts.

    Evaluation order (critical → least critical):
      1. Risk signals → block if any critical signal detected
      2. Confidence check → fail closed if too uncertain
      3. Domain scope → block if domain not in role's allowed list
      4. Action scope → block if action not in role's allowed list
      5. Otherwise → allow
    """

    # ── 1. Risk Signal Gate (highest priority) ────────────────────────────
    active_signals = [s for s in risk_signals if s != RiskSignal.NONE]
    critical_hits = [s for s in active_signals if s in CRITICAL_SIGNALS]

    if critical_hits:
        reason = f"Critical risk signal detected: {', '.join(s.value for s in critical_hits)}"
        logger.warning(f"BLOCKED (risk_signal): {reason}")
        return EvaluationResult(
            decision="block",
            reason=reason,
            blocked_by="risk_signal",
            risk_signals=active_signals,
        )

    # Non-critical risk signals (toxicity, obfuscation, sensitive entity)
    # Still block, but with softer messaging
    if active_signals:
        non_critical = [s for s in active_signals if s not in CRITICAL_SIGNALS]
        if non_critical and risk_score >= 0.7:
            reason = f"Risk signal elevated: {', '.join(s.value for s in non_critical)}"
            logger.warning(f"BLOCKED (elevated_risk): {reason}")
            return EvaluationResult(
                decision="block",
                reason=reason,
                blocked_by="elevated_risk",
                risk_signals=active_signals,
            )

    # ── 2. Confidence Gate (fail closed on uncertainty) ───────────────────
    min_confidence = min(action_confidence, domain_confidence)

    if min_confidence < AMBIGUITY_LOW:
        reason = f"Confidence too low (action={action_confidence:.2f}, domain={domain_confidence:.2f}). Denying by default."
        logger.warning(f"BLOCKED (low_confidence): {reason}")
        return EvaluationResult(
            decision="block",
            reason=reason,
            blocked_by="low_confidence",
            risk_signals=active_signals,
        )

    is_ambiguous = min_confidence < AMBIGUITY_HIGH

    # ── 3. Role Scope Enforcement ─────────────────────────────────────────
    scope = ROLE_SCOPES.get(role)

    if scope:
        # Domain confinement
        if scope.allowed_domains and domain not in scope.allowed_domains:
            reason = f"Domain '{domain.value}' is not in allowed domains for role '{role}'. Allowed: [{', '.join(d.value for d in scope.allowed_domains)}]"
            logger.warning(f"BLOCKED (domain_scope): {reason}")
            return EvaluationResult(
                decision="block",
                reason=reason,
                blocked_by="domain_scope",
                risk_signals=active_signals,
            )

        # Action confinement
        if scope.allowed_actions and action not in scope.allowed_actions:
            reason = f"Action '{action.value}' is not permitted for role '{role}'. Allowed: [{', '.join(a.value for a in scope.allowed_actions)}]"
            logger.warning(f"BLOCKED (action_scope): {reason}")
            return EvaluationResult(
                decision="block",
                reason=reason,
                blocked_by="action_scope",
                risk_signals=active_signals,
            )

    # ── 4. Ambiguity Flag ─────────────────────────────────────────────────
    if is_ambiguous:
        reason = f"Classification is ambiguous (action={action_confidence:.2f}, domain={domain_confidence:.2f}). Flagged for stricter review."
        logger.info(f"AMBIGUOUS: {reason}")
        return EvaluationResult(
            decision="ambiguous",
            reason=reason,
            blocked_by=None,
            risk_signals=active_signals,
        )

    # ── 5. Allow ──────────────────────────────────────────────────────────
    logger.info(f"ALLOWED: action={action.value} domain={domain.value} role={role}")
    return EvaluationResult(
        decision="allow",
        reason="Classification within scope. No risk signals detected.",
        blocked_by=None,
        risk_signals=active_signals,
    )
