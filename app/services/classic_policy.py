from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import re
import os

DEFAULT_POLICY_PATH = Path("app/policies/main.yaml")
POLICY_PATH = Path(
    os.getenv("GUARDRAIL_POLICY_PATH", str(DEFAULT_POLICY_PATH))
).expanduser()


class ClassicPolicyError(ValueError):
    """Raised when classic policy configuration is invalid."""


@dataclass
class RolePolicy:
    allow_all: bool
    allowed_intents: List[str]
    blocked_intents: List[str]


@dataclass
class ClassicPolicy:
    agent_name: str
    allowed_intents: List[str]
    blocked_intents: List[str]
    confidence_threshold: float
    confidence_fallback: str
    roles: Dict[str, RolePolicy]


def _normalize_intent_name(value: str) -> str:
    return str(value or "").strip().lower()


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for raw in values:
        normalized = _normalize_intent_name(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ClassicPolicyError(f"Policy file not found: {path}")

    raw_content = path.read_text(encoding="utf-8")

    try:
        import yaml
    except ImportError:
        parsed = _parse_minimal_policy_yaml(raw_content)
        if not isinstance(parsed, dict):
            raise ClassicPolicyError("Top-level policy YAML must be a mapping")
        return parsed

    try:
        parsed = yaml.safe_load(raw_content)
    except Exception as exc:
        raise ClassicPolicyError(f"Invalid YAML in {path}: {exc}") from exc

    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ClassicPolicyError("Top-level policy YAML must be a mapping")
    return parsed


def _strip_yaml_comment(line: str) -> str:
    """Strip inline comments while preserving quoted values."""
    in_single = False
    in_double = False
    output: List[str] = []
    for char in line:
        if char == "'" and not in_double:
            in_single = not in_single
            output.append(char)
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            output.append(char)
            continue
        if char == "#" and not in_single and not in_double:
            break
        output.append(char)
    return "".join(output).rstrip()


def _parse_scalar(value: str) -> Any:
    token = value.strip()
    if not token:
        return ""
    if (token.startswith('"') and token.endswith('"')) or (
        token.startswith("'") and token.endswith("'")
    ):
        token = token[1:-1]

    lower = token.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False

    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token


def _parse_minimal_policy_yaml(content: str) -> Dict[str, Any]:
    """
    Minimal parser for the classic policy schema.
    Supports the subset used by app/policies/main.yaml when PyYAML is unavailable.
    """
    parsed: Dict[str, Any] = {}
    section: str | None = None
    current_role: str | None = None
    current_role_list_key: str | None = None

    for raw_line in content.splitlines():
        clean_line = _strip_yaml_comment(raw_line)
        if not clean_line.strip():
            continue

        indent = len(clean_line) - len(clean_line.lstrip(" "))
        stripped = clean_line.strip()

        if indent == 0:
            current_role = None
            current_role_list_key = None
            if stripped.endswith(":"):
                section = stripped[:-1].strip()
                if section in {"agent", "confidence", "roles"}:
                    parsed.setdefault(section, {})
                elif section in {"allowed_intents", "blocked_intents"}:
                    parsed.setdefault(section, [])
                continue

            if ":" in stripped:
                key, raw_value = stripped.split(":", 1)
                parsed[key.strip()] = _parse_scalar(raw_value)
                section = None
                continue

            raise ClassicPolicyError(f"Unsupported YAML syntax: {raw_line}")

        if section == "agent" and indent >= 2 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            agent = parsed.setdefault("agent", {})
            if isinstance(agent, dict):
                agent[key.strip()] = _parse_scalar(raw_value)
            continue

        if section in {"allowed_intents", "blocked_intents"} and stripped.startswith("- "):
            values = parsed.setdefault(section, [])
            if isinstance(values, list):
                values.append(str(_parse_scalar(stripped[2:])))
            continue

        if section == "confidence" and indent >= 2 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            confidence = parsed.setdefault("confidence", {})
            if isinstance(confidence, dict):
                confidence[key.strip()] = _parse_scalar(raw_value)
            continue

        if section == "roles":
            roles = parsed.setdefault("roles", {})
            if not isinstance(roles, dict):
                continue

            if indent == 2 and stripped.endswith(":"):
                current_role = stripped[:-1].strip()
                current_role_list_key = None
                roles.setdefault(current_role, {})
                continue

            if current_role is None:
                continue

            role_cfg = roles.setdefault(current_role, {})
            if not isinstance(role_cfg, dict):
                continue

            if indent == 4 and ":" in stripped:
                key, raw_value = stripped.split(":", 1)
                key = key.strip()
                value = raw_value.strip()
                current_role_list_key = key
                if value:
                    role_cfg[key] = _parse_scalar(value)
                else:
                    role_cfg[key] = []
                continue

            if indent >= 6 and stripped.startswith("- "):
                list_key = current_role_list_key or "allow"
                list_values = role_cfg.setdefault(list_key, [])
                if isinstance(list_values, list):
                    list_values.append(str(_parse_scalar(stripped[2:])))
                continue

    return parsed


def load_classic_policy(path: Path = POLICY_PATH) -> ClassicPolicy:
    data = _load_yaml(path)

    agent = data.get("agent", {})
    if agent is None:
        agent = {}
    if not isinstance(agent, dict):
        raise ClassicPolicyError("'agent' must be a mapping")

    agent_name = str(agent.get("name", "default-agent")).strip() or "default-agent"

    allowed_intents = data.get("allowed_intents", [])
    blocked_intents = data.get("blocked_intents", [])
    if not isinstance(allowed_intents, list):
        raise ClassicPolicyError("'allowed_intents' must be a list")
    if not isinstance(blocked_intents, list):
        raise ClassicPolicyError("'blocked_intents' must be a list")

    normalized_allowed = _dedupe([str(item) for item in allowed_intents])
    normalized_blocked = _dedupe([str(item) for item in blocked_intents])

    overlap = sorted(set(normalized_allowed) & set(normalized_blocked))
    if overlap:
        raise ClassicPolicyError(
            f"Intents cannot be both allowed and blocked: {', '.join(overlap)}"
        )

    confidence = data.get("confidence", {})
    if confidence is None:
        confidence = {}
    if not isinstance(confidence, dict):
        raise ClassicPolicyError("'confidence' must be a mapping")

    threshold_raw = confidence.get("threshold", 0.6)
    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError) as exc:
        raise ClassicPolicyError("confidence.threshold must be numeric") from exc
    if threshold < 0.0 or threshold > 1.0:
        raise ClassicPolicyError("confidence.threshold must be in [0, 1]")

    fallback = _normalize_intent_name(str(confidence.get("fallback", "block")))
    if fallback not in {"block", "allow"}:
        raise ClassicPolicyError("confidence.fallback must be 'block' or 'allow'")

    roles_raw = data.get("roles", {})
    if roles_raw is None:
        roles_raw = {}
    if not isinstance(roles_raw, dict):
        raise ClassicPolicyError("'roles' must be a mapping")

    roles: Dict[str, RolePolicy] = {}
    for role_name, role_cfg in roles_raw.items():
        role = _normalize_intent_name(str(role_name))
        if not role:
            continue
        if not isinstance(role_cfg, dict):
            raise ClassicPolicyError(f"Role '{role}' must be a mapping")

        allow_value = role_cfg.get("allow", [])
        block_value = role_cfg.get("block", [])
        if isinstance(allow_value, str) and allow_value.strip().upper() == "ALL":
            roles[role] = RolePolicy(allow_all=True, allowed_intents=[], blocked_intents=[])
            continue

        if not isinstance(allow_value, list):
            raise ClassicPolicyError(f"Role '{role}' allow must be a list or ALL")
        if not isinstance(block_value, list):
            raise ClassicPolicyError(f"Role '{role}' block must be a list")
        roles[role] = RolePolicy(
            allow_all=False,
            allowed_intents=_dedupe([str(v) for v in allow_value]),
            blocked_intents=_dedupe([str(v) for v in block_value]),
        )

    return ClassicPolicy(
        agent_name=agent_name,
        allowed_intents=normalized_allowed,
        blocked_intents=normalized_blocked,
        confidence_threshold=threshold,
        confidence_fallback=fallback,
        roles=roles,
    )


_INTENT_ALIAS_MAP = {
    "policy.financial_advice": "financial.advice",
    "info.query.pii": "security.pii_exfiltration",
    "security.jailbreak": "security.jailbreak",
    "code.exploit": "security.prompt_injection",
    "sys.control": "security.system_override",
}


def infer_policy_intent(base_intent: str, text: str) -> str:
    intent = _normalize_intent_name(base_intent)
    text_lower = (text or "").lower()

    if any(token in text_lower for token in ("schedule interview", "interview schedule", "book interview")):
        return "interview.scheduling"
    if any(token in text_lower for token in ("screen candidate", "candidate screening", "screening")):
        return "candidate.screening"
    if any(token in text_lower for token in ("recruit", "hiring", "candidate", "job description")):
        return "recruitment.question"
    if any(
        token in text_lower
        for token in ("debug", "bug", "exception", "traceback", "error", "fix this")
    ):
        return "debugging.help"
    if any(token in text_lower for token in ("review this code", "code review", "review my code")):
        return "code.review"
    if any(
        token in text_lower
        for token in (
            "code",
            "function",
            "class",
            "constructor",
            "contructor",
            "algorithm",
            "python",
            "javascript",
            "java",
            "typescript",
            "c++",
            "golang",
            "rust",
        )
    ):
        return "coding.question"

    if any(token in text_lower for token in ("stock", "crypto", "investment", "trading", "portfolio")):
        return "financial.advice"
    if any(token in text_lower for token in ("election", "political", "party", "government", "vote")):
        return "political.discussion"
    if any(token in text_lower for token in ("medical", "diagnose", "prescription", "doctor", "treatment")):
        return "medical.advice"
    if re.match(r"^\s*(what|who|when|where|why|how|define|explain|tell me)\b", text_lower):
        return "info.query"
    if text_lower.strip().endswith("?"):
        return "info.query"

    return _INTENT_ALIAS_MAP.get(intent, intent or "unknown")


def evaluate_classic_policy(
    policy: ClassicPolicy,
    *,
    role: str,
    detected_intent: str,
    confidence: float,
    text: str,
) -> Dict[str, str]:
    normalized_role = _normalize_intent_name(role) or "general"
    policy_intent = infer_policy_intent(detected_intent, text)

    role_policy = policy.roles.get(normalized_role)
    if role_policy and role_policy.allow_all:
        return {
            "decision": "allow",
            "reason": f"Role '{normalized_role}' bypass (ALL).",
            "policy_intent": policy_intent,
        }

    if confidence < policy.confidence_threshold:
        if policy.confidence_fallback == "block":
            return {
                "decision": "block",
                "reason": (
                    f"Confidence {confidence:.2f} below threshold {policy.confidence_threshold:.2f}"
                ),
                "policy_intent": policy_intent,
            }

    if policy_intent in policy.blocked_intents:
        return {
            "decision": "block",
            "reason": f"Blocked intent: {policy_intent}",
            "policy_intent": policy_intent,
        }

    if policy.allowed_intents and policy_intent not in policy.allowed_intents:
        return {
            "decision": "block",
            "reason": f"Intent not in allowlist: {policy_intent}",
            "policy_intent": policy_intent,
        }

    if role_policy and role_policy.allowed_intents and policy_intent not in role_policy.allowed_intents:
        return {
            "decision": "block",
            "reason": f"Role '{normalized_role}' does not allow intent: {policy_intent}",
            "policy_intent": policy_intent,
        }
    if role_policy and policy_intent in role_policy.blocked_intents:
        return {
            "decision": "block",
            "reason": f"Role '{normalized_role}' blocked intent: {policy_intent}",
            "policy_intent": policy_intent,
        }

    return {
        "decision": "allow",
        "reason": "Policy allow.",
        "policy_intent": policy_intent,
    }
