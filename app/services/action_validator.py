"""
Action Validator — Post-LLM Structured Action Extraction & Validation.

This component sits BETWEEN the LLM response and execution.
It extracts structured action proposals from the LLM output
and validates each one against the Policy Engine.

Supports:
  - OpenAI tool_calls / function_call format
  - Anthropic tool_use content blocks
  - Raw JSON extraction from text (fallback)
  - Rejection of free-form text that appears to trigger tools

Key principle:
  Free-form text should NEVER directly trigger a tool.
  Only structured, validated proposals are allowed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas.action import ActionDecision, ActionProposal
from app.services.policy_engine import PolicyEngine

logger = logging.getLogger(__name__)

# Pattern to find JSON objects in text (for fallback extraction)
_JSON_BLOCK_PATTERN = re.compile(
    r"```(?:json)?\s*(\{[\s\S]*?\})\s*```"  # fenced code blocks
    r"|(\{[^{}]*\"(?:intent|tool|action)\"[^{}]*\})",  # inline JSON with action keys
    re.MULTILINE,
)


class ActionValidator:
    """
    Extracts structured actions from LLM responses and validates
    them against the Policy Engine.
    """

    def __init__(self, policy_engine: PolicyEngine) -> None:
        self._engine = policy_engine

    # ── Extraction ────────────────────────────────────────────────────────

    def extract_actions(self, llm_response: dict[str, Any]) -> list[ActionProposal]:
        """
        Extract structured action proposals from an LLM response.

        Tries these extraction methods in order:
          1. OpenAI tool_calls (ChatCompletion format)
          2. OpenAI function_call (legacy format)
          3. Anthropic tool_use content blocks
          4. Raw JSON extraction from text (conservative fallback)

        Returns empty list if no structured actions found.
        """
        actions: list[ActionProposal] = []
        method = "none"

        # 1. OpenAI tool_calls (modern format)
        choices = llm_response.get("choices", [])
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}

            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                method = "tool_calls"
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        params = json.loads(fn.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        params = {}
                    if tool_name:
                        actions.append(ActionProposal(tool=tool_name, parameters=params))

            # 2. OpenAI function_call (legacy)
            if not actions:
                fn_call = message.get("function_call")
                if isinstance(fn_call, dict):
                    method = "function_call"
                    tool_name = fn_call.get("name", "")
                    try:
                        params = json.loads(fn_call.get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        params = {}
                    if tool_name:
                        actions.append(ActionProposal(tool=tool_name, parameters=params))

        # 3. Anthropic tool_use content blocks
        if not actions:
            content = llm_response.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        method = "tool_use"
                        tool_name = block.get("name", "")
                        params = block.get("input", {})
                        if tool_name:
                            actions.append(ActionProposal(tool=tool_name, parameters=params))

        # 4. JSON extraction from text (conservative fallback)
        if not actions:
            text_content = self._extract_text_content(llm_response)
            if text_content:
                extracted = self._extract_json_actions(text_content)
                if extracted:
                    method = "json_parse"
                    actions.extend(extracted)

        if actions:
            logger.info(
                "Extracted %d action(s) via %s: %s",
                len(actions), method, [a.tool for a in actions],
            )

        return actions

    def _extract_text_content(self, llm_response: dict[str, Any]) -> str:
        """Extract text content from various LLM response formats."""
        # OpenAI format
        choices = llm_response.get("choices", [])
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content")
            if isinstance(content, str):
                return content

        # Anthropic format
        content = llm_response.get("content", [])
        if isinstance(content, list):
            texts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            if texts:
                return "\n".join(texts)

        # Direct text
        if isinstance(content, str):
            return content

        return ""

    def _extract_json_actions(self, text: str) -> list[ActionProposal]:
        """
        Conservative extraction of JSON action proposals from text.

        Only extracts if the JSON explicitly contains 'tool' or 'intent' keys,
        indicating a structured action proposal.
        """
        actions: list[ActionProposal] = []

        for match in _JSON_BLOCK_PATTERN.finditer(text):
            json_str = match.group(1) or match.group(2)
            if not json_str:
                continue
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            # Must have a tool/intent/action key
            tool_name = data.get("tool") or data.get("intent") or data.get("action")
            if not isinstance(tool_name, str) or not tool_name:
                continue

            params = data.get("parameters", data.get("params", data.get("input", {})))
            if not isinstance(params, dict):
                params = {}

            actions.append(ActionProposal(
                tool=tool_name,
                parameters=params,
                reasoning=data.get("reasoning"),
            ))

        return actions

    # ── Validation ────────────────────────────────────────────────────────

    def validate_actions(
        self,
        proposals: list[ActionProposal],
        role: str = "general",
        session_action_count: int = 0,
        session_chain_depth: int = 0,
    ) -> list[ActionDecision]:
        """
        Validate a list of action proposals against the policy engine.

        Returns a parallel list of ActionDecisions.
        """
        decisions: list[ActionDecision] = []
        for proposal in proposals:
            decision = self._engine.evaluate_action(
                proposal,
                role=role,
                session_action_count=session_action_count + len(decisions),
                session_chain_depth=session_chain_depth,
            )
            decisions.append(decision)
            if not decision.allowed:
                logger.warning(
                    "Action BLOCKED: tool=%s reason=%s",
                    proposal.tool, decision.reason,
                )
        return decisions

    def validate_and_filter_response(
        self,
        llm_response: dict[str, Any],
        role: str = "general",
        session_action_count: int = 0,
        session_chain_depth: int = 0,
    ) -> tuple[dict[str, Any], list[ActionDecision], list[ActionProposal]]:
        """
        Full pipeline: extract → validate → filter blocked actions from response.

        Returns:
          - Modified LLM response with blocked actions removed
          - List of all decisions
          - List of all proposals
        """
        proposals = self.extract_actions(llm_response)

        if not proposals:
            return llm_response, [], []

        decisions = self.validate_actions(
            proposals,
            role=role,
            session_action_count=session_action_count,
            session_chain_depth=session_chain_depth,
        )

        # Filter blocked tool_calls from the response
        blocked_tools = {
            proposals[i].tool
            for i, d in enumerate(decisions)
            if not d.allowed
        }

        if blocked_tools:
            filtered = self._filter_response(llm_response, blocked_tools)
            return filtered, decisions, proposals

        return llm_response, decisions, proposals

    def _filter_response(
        self,
        llm_response: dict[str, Any],
        blocked_tools: set[str],
    ) -> dict[str, Any]:
        """Remove blocked tool calls from the LLM response."""
        response = dict(llm_response)

        # Filter OpenAI tool_calls
        choices = response.get("choices", [])
        if choices and isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message", {})
                if not isinstance(message, dict):
                    continue

                tool_calls = message.get("tool_calls", [])
                if tool_calls:
                    message["tool_calls"] = [
                        tc for tc in tool_calls
                        if isinstance(tc, dict)
                        and tc.get("function", {}).get("name") not in blocked_tools
                    ]

                # Filter legacy function_call
                fn_call = message.get("function_call")
                if isinstance(fn_call, dict) and fn_call.get("name") in blocked_tools:
                    del message["function_call"]

        # Filter Anthropic tool_use
        content = response.get("content", [])
        if isinstance(content, list):
            response["content"] = [
                block for block in content
                if not (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") in blocked_tools
                )
            ]

        return response
