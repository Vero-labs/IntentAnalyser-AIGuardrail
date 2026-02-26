"""
Tool Registry — Central catalog of all tools an agent can use.

Every tool is mapped to one or more Capabilities.
The Policy Engine validates proposed actions against this registry.

The registry is the single source of truth for:
  - What tools exist
  - What capabilities they require
  - What parameter schemas are expected
  - What scope constraints apply (channels, tables, endpoints, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.capabilities import Capability

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """A registered tool that an agent can propose to use."""
    name: str                                       # "slack.send", "db.read"
    capabilities: list[Capability]                  # Required capabilities
    parameter_schema: dict[str, Any] = field(       # JSON Schema for params
        default_factory=dict,
    )
    scope_constraints: dict[str, list[str]] = field(  # Allowed values per param
        default_factory=dict,
    )
    description: str = ""                            # Human-readable description
    rate_limit: int | None = None                     # Max calls per minute (None = unlimited)


class ToolRegistry:
    """Thread-safe registry of tool definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition. Overwrites if name already exists."""
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool registration: %s", tool.name)
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s (capabilities=%s)", tool.name, [c.value for c in tool.capabilities])

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_all(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_capability(self, capability: Capability) -> list[ToolDefinition]:
        """List tools that require a specific capability."""
        return [t for t in self._tools.values() if capability in t.capabilities]

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def validate_scope(self, tool_name: str, parameters: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate that proposed parameters fall within the tool's scope constraints.

        Returns (is_valid, reason).
        """
        tool = self.get(tool_name)
        if tool is None:
            return False, f"Unknown tool: {tool_name}"

        for param_key, allowed_values in tool.scope_constraints.items():
            proposed_value = parameters.get(param_key)
            if proposed_value is None:
                continue  # Missing param is a schema issue, not scope
            if isinstance(proposed_value, str):
                if proposed_value not in allowed_values:
                    return False, (
                        f"Parameter '{param_key}' value '{proposed_value}' "
                        f"is not in allowed scope: {allowed_values}"
                    )
            elif isinstance(proposed_value, list):
                for val in proposed_value:
                    if val not in allowed_values:
                        return False, (
                            f"Parameter '{param_key}' contains '{val}' "
                            f"which is not in allowed scope: {allowed_values}"
                        )

        return True, "Within scope"

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ── Default tool definitions (common examples) ───────────────────────────────

DEFAULT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="slack.send",
        capabilities=[Capability.NOTIFY],
        parameter_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["channel", "message"],
        },
        scope_constraints={"channel": ["#ops", "#alerts", "#general"]},
        description="Send a message to a Slack channel",
    ),
    ToolDefinition(
        name="db.read",
        capabilities=[Capability.READ],
        parameter_schema={
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["table"],
        },
        scope_constraints={"table": ["employees", "projects", "tasks"]},
        description="Read records from a database table",
    ),
    ToolDefinition(
        name="db.write",
        capabilities=[Capability.WRITE],
        parameter_schema={
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["table", "data"],
        },
        scope_constraints={"table": ["tasks", "notes"]},
        description="Write a record to a database table",
    ),
    ToolDefinition(
        name="db.delete",
        capabilities=[Capability.DELETE],
        parameter_schema={
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "record_id": {"type": "string"},
            },
            "required": ["table", "record_id"],
        },
        scope_constraints={},
        description="Delete a record from a database table",
    ),
    ToolDefinition(
        name="email.send",
        capabilities=[Capability.NOTIFY],
        parameter_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        scope_constraints={},
        description="Send an email",
    ),
    ToolDefinition(
        name="http.request",
        capabilities=[Capability.EXECUTE_EXTERNAL],
        parameter_schema={
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                "url": {"type": "string"},
                "body": {"type": "object"},
            },
            "required": ["method", "url"],
        },
        scope_constraints={},
        description="Make an outbound HTTP request",
    ),
    ToolDefinition(
        name="secret.read",
        capabilities=[Capability.ACCESS_SECRET],
        parameter_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
            },
            "required": ["key"],
        },
        scope_constraints={},
        description="Read a secret or credential by key",
    ),
]


def build_default_registry() -> ToolRegistry:
    """Build a registry pre-loaded with default tool definitions."""
    registry = ToolRegistry()
    for tool in DEFAULT_TOOLS:
        registry.register(tool)
    return registry
