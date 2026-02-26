"""
Policy Engine v2 — Deterministic Action Validation.

Pure structural logic. No ML, no heuristics.
Takes a structured ActionProposal and evaluates it against
declarative capability-scoped tool policies.

This is the heart of the control plane.

Evaluation order:
  1. Tool exists in registry?
  2. Capability allowed for this agent?
  3. Tool explicitly allowed/denied?
  4. Parameters within scope constraints?
  5. Sandbox limits not exceeded?
  → Allow or Block (deterministic, no AI)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.capabilities import Capability
from app.core.tool_registry import ToolRegistry
from app.schemas.action import ActionDecision, ActionProposal

logger = logging.getLogger(__name__)


@dataclass
class ToolPolicy:
    """Policy rule for a specific tool."""
    tool: str                                       # "slack.send"
    allowed: bool = True                            # Explicit allow/deny
    scope_overrides: dict[str, list[str]] = field(  # Override scope from registry
        default_factory=dict,
    )


@dataclass
class SandboxConfig:
    """Runtime containment limits for autonomous agents."""
    max_actions_per_session: int = 20
    max_chain_depth: int = 5
    timeout_seconds: int = 120
    budget_limit_usd: float = 1.00


@dataclass
class AgentPolicy:
    """Complete policy definition for one agent."""
    agent_name: str
    allowed_capabilities: list[Capability] = field(default_factory=list)
    denied_capabilities: list[Capability] = field(default_factory=list)
    tool_policies: list[ToolPolicy] = field(default_factory=list)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)

    def get_tool_policy(self, tool_name: str) -> ToolPolicy | None:
        """Find a specific tool policy by name."""
        for tp in self.tool_policies:
            if tp.tool == tool_name:
                return tp
        return None


class PolicyEngine:
    """
    Deterministic policy evaluation engine.

    No AI in this layer. Pure rule-based validation:
      1. Check tool exists
      2. Check capability is allowed
      3. Check tool is not explicitly denied
      4. Check parameters within scope
    """

    def __init__(self, registry: ToolRegistry, policy: AgentPolicy) -> None:
        self._registry = registry
        self._policy = policy

    @property
    def policy(self) -> AgentPolicy:
        return self._policy

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def evaluate_action(
        self,
        proposal: ActionProposal,
        role: str = "general",
        session_action_count: int = 0,
        session_chain_depth: int = 0,
    ) -> ActionDecision:
        """
        Evaluate one action proposal against the policy.

        Returns a deterministic ActionDecision.
        """

        # ── 1. Tool exists? ───────────────────────────────────────────────
        tool_def = self._registry.get(proposal.tool)
        if tool_def is None:
            logger.warning("BLOCKED (unknown_tool): %s", proposal.tool)
            return ActionDecision(
                tool=proposal.tool,
                allowed=False,
                reason=f"Unknown tool: '{proposal.tool}'. Not registered in tool registry.",
                policy_rule="unknown_tool",
            )

        # ── 2. Capability allowed? ────────────────────────────────────────
        for cap in tool_def.capabilities:
            if cap in self._policy.denied_capabilities:
                logger.warning(
                    "BLOCKED (denied_capability): tool=%s capability=%s",
                    proposal.tool, cap.value,
                )
                return ActionDecision(
                    tool=proposal.tool,
                    allowed=False,
                    reason=f"Capability '{cap.value}' is denied by policy.",
                    capability=cap.value,
                    policy_rule="denied_capability",
                )

            if self._policy.allowed_capabilities and cap not in self._policy.allowed_capabilities:
                logger.warning(
                    "BLOCKED (capability_not_allowed): tool=%s capability=%s",
                    proposal.tool, cap.value,
                )
                return ActionDecision(
                    tool=proposal.tool,
                    allowed=False,
                    reason=(
                        f"Capability '{cap.value}' is not in the allowed list. "
                        f"Allowed: {[c.value for c in self._policy.allowed_capabilities]}"
                    ),
                    capability=cap.value,
                    policy_rule="capability_not_allowed",
                )

        # ── 3. Tool explicitly denied? ────────────────────────────────────
        tool_policy = self._policy.get_tool_policy(proposal.tool)
        if tool_policy is not None and not tool_policy.allowed:
            logger.warning("BLOCKED (tool_denied): %s", proposal.tool)
            return ActionDecision(
                tool=proposal.tool,
                allowed=False,
                reason=f"Tool '{proposal.tool}' is explicitly denied by policy.",
                capability=tool_def.capabilities[0].value if tool_def.capabilities else None,
                policy_rule="tool_denied",
            )

        # ── 4. Scope constraints ──────────────────────────────────────────
        # Use tool_policy scope overrides if available, otherwise registry defaults
        effective_scope = dict(tool_def.scope_constraints)
        if tool_policy and tool_policy.scope_overrides:
            effective_scope.update(tool_policy.scope_overrides)

        for param_key, allowed_values in effective_scope.items():
            proposed_value = proposal.parameters.get(param_key)
            if proposed_value is None:
                continue

            values_to_check = [proposed_value] if isinstance(proposed_value, str) else (
                proposed_value if isinstance(proposed_value, list) else [str(proposed_value)]
            )
            for val in values_to_check:
                if val not in allowed_values:
                    logger.warning(
                        "BLOCKED (scope_violation): tool=%s param=%s value=%s allowed=%s",
                        proposal.tool, param_key, val, allowed_values,
                    )
                    return ActionDecision(
                        tool=proposal.tool,
                        allowed=False,
                        reason=(
                            f"Scope violation: parameter '{param_key}' value '{val}' "
                            f"is not in allowed values: {allowed_values}"
                        ),
                        capability=tool_def.capabilities[0].value if tool_def.capabilities else None,
                        policy_rule="scope_violation",
                        scope_violation=f"{param_key}={val}",
                    )

        # ── 5. Sandbox limits ─────────────────────────────────────────────
        sandbox = self._policy.sandbox
        if session_action_count >= sandbox.max_actions_per_session:
            logger.warning(
                "BLOCKED (sandbox_action_limit): count=%d max=%d",
                session_action_count, sandbox.max_actions_per_session,
            )
            return ActionDecision(
                tool=proposal.tool,
                allowed=False,
                reason=(
                    f"Session action limit exceeded: {session_action_count} "
                    f">= {sandbox.max_actions_per_session}"
                ),
                policy_rule="sandbox_action_limit",
            )

        if session_chain_depth >= sandbox.max_chain_depth:
            logger.warning(
                "BLOCKED (sandbox_chain_depth): depth=%d max=%d",
                session_chain_depth, sandbox.max_chain_depth,
            )
            return ActionDecision(
                tool=proposal.tool,
                allowed=False,
                reason=(
                    f"Chain depth limit exceeded: {session_chain_depth} "
                    f">= {sandbox.max_chain_depth}"
                ),
                policy_rule="sandbox_chain_depth",
            )

        # ── 6. Allow ──────────────────────────────────────────────────────
        primary_cap = tool_def.capabilities[0].value if tool_def.capabilities else "unknown"
        logger.info(
            "ALLOWED: tool=%s capability=%s role=%s",
            proposal.tool, primary_cap, role,
        )
        return ActionDecision(
            tool=proposal.tool,
            allowed=True,
            reason="Action is within policy scope.",
            capability=primary_cap,
            policy_rule="allowed",
        )


# ── Use-case preset policies ─────────────────────────────────────────────────

PRESET_POLICIES: dict[str, AgentPolicy] = {
    "public_chatbot": AgentPolicy(
        agent_name="public-chatbot",
        allowed_capabilities=[Capability.READ, Capability.NOTIFY],
        denied_capabilities=[Capability.DELETE, Capability.EXECUTE_EXTERNAL, Capability.ACCESS_SECRET],
        sandbox=SandboxConfig(max_actions_per_session=10, max_chain_depth=3),
    ),
    "internal_assistant": AgentPolicy(
        agent_name="internal-assistant",
        allowed_capabilities=[Capability.READ, Capability.WRITE, Capability.NOTIFY],
        denied_capabilities=[Capability.DELETE, Capability.EXECUTE_EXTERNAL, Capability.ACCESS_SECRET],
        sandbox=SandboxConfig(max_actions_per_session=20, max_chain_depth=5),
    ),
    "developer_tool": AgentPolicy(
        agent_name="developer-tool",
        allowed_capabilities=[Capability.READ, Capability.WRITE, Capability.EXECUTE_EXTERNAL],
        denied_capabilities=[Capability.DELETE, Capability.ACCESS_SECRET],
        sandbox=SandboxConfig(max_actions_per_session=50, max_chain_depth=10),
    ),
}


def load_policy_from_config(config: dict[str, Any]) -> AgentPolicy:
    """
    Load an AgentPolicy from the guardrail config dict.

    Expected config shape:
      capabilities:
        allowed: [read, notify]
        denied: [delete, access_secret]
      tools:
        - name: slack.send
          allowed: true
          scope:
            channels: ["#ops"]
      sandbox:
        max_actions_per_session: 20
        max_chain_depth: 5
        timeout_seconds: 120
        budget_limit_usd: 1.00
    """
    # Capabilities
    cap_config = config.get("capabilities", {})
    allowed_caps = [Capability(c) for c in cap_config.get("allowed", [])]
    denied_caps = [Capability(c) for c in cap_config.get("denied", [])]

    # Tool policies
    tool_policies = []
    for tool_conf in config.get("tools", []):
        tp = ToolPolicy(
            tool=tool_conf["name"],
            allowed=tool_conf.get("allowed", True),
            scope_overrides=tool_conf.get("scope", {}),
        )
        tool_policies.append(tp)

    # Sandbox
    sandbox_conf = config.get("sandbox", {})
    sandbox = SandboxConfig(
        max_actions_per_session=sandbox_conf.get("max_actions_per_session", 20),
        max_chain_depth=sandbox_conf.get("max_chain_depth", 5),
        timeout_seconds=sandbox_conf.get("timeout_seconds", 120),
        budget_limit_usd=sandbox_conf.get("budget_limit_usd", 1.00),
    )

    agent_name = config.get("agent", {}).get("name", "default-agent")

    return AgentPolicy(
        agent_name=agent_name,
        allowed_capabilities=allowed_caps,
        denied_capabilities=denied_caps,
        tool_policies=tool_policies,
        sandbox=sandbox,
    )
