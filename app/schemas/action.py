"""
Structured Action Protocol — Schemas.

The contract between the LLM (data plane) and the control plane.
The LLM NEVER executes anything directly — it can only propose
actions in structured form. The control plane validates every proposal.

Key models:
  - ActionProposal:  What the LLM wants to do
  - ActionDecision:  What the control plane decided
  - AuditEvent:      Full audit trail for one request
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActionProposal(BaseModel):
    """Structured action proposed by the LLM."""
    tool: str                                       # "slack.send", "db.read"
    parameters: dict[str, Any] = Field(             # {"channel": "#ops", "message": "..."}
        default_factory=dict,
    )
    reasoning: Optional[str] = None                 # Optional LLM reasoning for audit

    def __str__(self) -> str:
        return f"{self.tool}({self.parameters})"


class ActionDecision(BaseModel):
    """Deterministic decision from the Policy Engine."""
    tool: str                                       # Which tool was proposed
    allowed: bool                                   # Allow or deny
    reason: str                                     # Why (human-readable)
    capability: Optional[str] = None                # Which capability class
    policy_rule: Optional[str] = None               # Which policy rule triggered
    scope_violation: Optional[str] = None           # Scope constraint that failed

    @property
    def decision(self) -> str:
        return "allow" if self.allowed else "block"


class AuditEvent(BaseModel):
    """
    Full audit trail for one request through the control plane.

    Every step is recorded:
      1. Original prompt
      2. Input guard decision
      3. LLM output
      4. Proposed action(s)
      5. Policy evaluation result(s)
      6. Execution result (if allowed)
    """
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    session_id: str = ""
    request_id: str = ""

    # Step 1: Input
    original_prompt: str = ""

    # Step 2: Input Guard (pre-LLM)
    input_guard_decision: str = "allow"              # "allow", "block"
    input_guard_reason: Optional[str] = None
    input_guard_intent: Optional[str] = None
    input_guard_confidence: Optional[float] = None

    # Step 3: LLM Output
    llm_response_text: Optional[str] = None

    # Step 4: Action Extraction
    proposed_actions: list[ActionProposal] = Field(default_factory=list)
    action_extraction_method: Optional[str] = None   # "tool_calls", "function_call", "json_parse", "none"

    # Step 5: Policy Evaluation
    action_decisions: list[ActionDecision] = Field(default_factory=list)

    # Step 6: Execution
    execution_results: list[dict[str, Any]] = Field(default_factory=list)

    # Timing
    total_time_ms: float = 0.0
    input_guard_time_ms: float = 0.0
    llm_time_ms: float = 0.0
    policy_eval_time_ms: float = 0.0

    # Sandbox
    session_action_count: int = 0
    session_chain_depth: int = 0


class ActionValidationRequest(BaseModel):
    """Direct action validation request (no LLM involved)."""
    tool: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    role: str = "general"
    session_id: Optional[str] = None


class ActionValidationResponse(BaseModel):
    """Response to a direct action validation request."""
    tool: str
    allowed: bool
    reason: str
    capability: Optional[str] = None
    policy_rule: Optional[str] = None
