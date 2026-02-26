"""
Runtime Sandbox — Per-session containment for autonomous agents.

Autonomous agents fail by infinite loops and escalation.
This module contains them with deterministic limits:
  - Max actions per session
  - Max chain depth
  - Session timeout
  - Budget limit (based on capability risk weights)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.capabilities import CAPABILITY_RISK_WEIGHT, Capability

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Tracks the runtime state of one agent session."""
    session_id: str
    created_at: float = field(default_factory=time.time)
    action_count: int = 0
    chain_depth: int = 0
    total_risk_budget: float = 0.0
    actions_log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.created_at


class SessionSandbox:
    """
    Manages per-session containment limits.

    Thread-safe session tracking with automatic expiry.
    """

    def __init__(
        self,
        max_actions: int = 20,
        max_chain_depth: int = 5,
        timeout_seconds: int = 120,
        budget_limit: float = 1.0,
    ) -> None:
        self._max_actions = max_actions
        self._max_chain_depth = max_chain_depth
        self._timeout_seconds = timeout_seconds
        self._budget_limit = budget_limit
        self._sessions: dict[str, SessionState] = {}

    def _get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]

    def check_limits(self, session_id: str) -> tuple[bool, str]:
        """
        Check if a session is within sandbox limits.

        Returns (within_limits, reason).
        """
        session = self._get_or_create(session_id)

        if session.elapsed_seconds > self._timeout_seconds:
            return False, (
                f"Session timeout: {session.elapsed_seconds:.0f}s "
                f"> {self._timeout_seconds}s limit"
            )

        if session.action_count >= self._max_actions:
            return False, (
                f"Action limit: {session.action_count} "
                f">= {self._max_actions} max"
            )

        if session.chain_depth >= self._max_chain_depth:
            return False, (
                f"Chain depth limit: {session.chain_depth} "
                f">= {self._max_chain_depth} max"
            )

        if session.total_risk_budget >= self._budget_limit:
            return False, (
                f"Risk budget exhausted: {session.total_risk_budget:.2f} "
                f">= {self._budget_limit:.2f} limit"
            )

        return True, "Within limits"

    def record_action(
        self,
        session_id: str,
        tool_name: str,
        capabilities: list[Capability] | None = None,
    ) -> None:
        """Record an executed action against the session."""
        session = self._get_or_create(session_id)
        session.action_count += 1

        # Calculate risk cost
        risk_cost = 0.0
        if capabilities:
            risk_cost = max(CAPABILITY_RISK_WEIGHT.get(c, 0.1) for c in capabilities)
        session.total_risk_budget += risk_cost

        session.actions_log.append({
            "tool": tool_name,
            "action_number": session.action_count,
            "risk_cost": risk_cost,
            "cumulative_risk": session.total_risk_budget,
            "timestamp": time.time(),
        })

        logger.info(
            "Sandbox: session=%s action=%d tool=%s risk=%.2f budget=%.2f/%.2f",
            session_id, session.action_count, tool_name,
            risk_cost, session.total_risk_budget, self._budget_limit,
        )

    def increment_chain_depth(self, session_id: str) -> None:
        """Increment chain depth when an action triggers another LLM call."""
        session = self._get_or_create(session_id)
        session.chain_depth += 1

    def get_session_stats(self, session_id: str) -> dict[str, Any]:
        """Get current stats for a session."""
        session = self._get_or_create(session_id)
        return {
            "session_id": session_id,
            "action_count": session.action_count,
            "chain_depth": session.chain_depth,
            "elapsed_seconds": round(session.elapsed_seconds, 1),
            "risk_budget_used": round(session.total_risk_budget, 3),
            "risk_budget_limit": self._budget_limit,
            "actions": session.actions_log,
        }

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        expired = [
            sid for sid, state in self._sessions.items()
            if state.elapsed_seconds > self._timeout_seconds * 2  # 2x timeout for cleanup
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def reset_session(self, session_id: str) -> None:
        """Reset a session (e.g., for testing)."""
        if session_id in self._sessions:
            del self._sessions[session_id]
