from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
import os

DEFAULT_CONFIG_PATH = Path("guardrail.config.yaml")
CONFIG_PATH = Path(
    os.getenv("GUARDRAIL_CONFIG_PATH", str(DEFAULT_CONFIG_PATH))
).expanduser()


class RuntimeConfigError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass
class RuntimeConfig:
    provider_name: str
    provider_model: str
    provider_base_url: str
    provider_api_key_env: str
    server_host: str
    server_port: int
    policy_mode: str
    request_timeout_seconds: float
    prompt_logging_enabled: bool


def default_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        provider_name="openai",
        provider_model="gpt-4o-mini",
        provider_base_url="https://api.openai.com",
        provider_api_key_env="OPENAI_API_KEY",
        server_host="0.0.0.0",
        server_port=8000,
        policy_mode="custom",
        request_timeout_seconds=60.0,
        prompt_logging_enabled=False,
    )


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeConfigError(f"Config file not found: {path}")

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeConfigError(
            "PyYAML is required to load guardrail.config.yaml"
        ) from exc

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise RuntimeConfigError("guardrail.config.yaml must be a top-level mapping")
    return raw


def load_runtime_config(path: Path = CONFIG_PATH) -> RuntimeConfig:
    raw = _load_yaml(path)

    provider = raw.get("provider", {})
    if provider is None:
        provider = {}
    if not isinstance(provider, dict):
        raise RuntimeConfigError("'provider' must be a mapping")

    server = raw.get("server", {})
    if server is None:
        server = {}
    if not isinstance(server, dict):
        raise RuntimeConfigError("'server' must be a mapping")

    logging_cfg = raw.get("logging", {})
    if logging_cfg is None:
        logging_cfg = {}
    if not isinstance(logging_cfg, dict):
        raise RuntimeConfigError("'logging' must be a mapping")

    provider_name = str(provider.get("name", "openai")).strip().lower()
    if provider_name not in {"openai", "anthropic", "azure", "custom"}:
        raise RuntimeConfigError("provider.name must be one of: openai, anthropic, azure, custom")

    provider_model = str(provider.get("model", "")).strip()
    if not provider_model:
        raise RuntimeConfigError("provider.model is required")

    provider_base_url = str(provider.get("base_url", "https://api.openai.com")).strip().rstrip("/")
    if not provider_base_url:
        raise RuntimeConfigError("provider.base_url is required")

    provider_api_key_env = str(provider.get("api_key_env", "OPENAI_API_KEY")).strip()
    if not provider_api_key_env:
        raise RuntimeConfigError("provider.api_key_env is required")

    server_host = str(server.get("host", "0.0.0.0")).strip() or "0.0.0.0"

    try:
        server_port = int(server.get("port", 8000))
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigError("server.port must be an integer") from exc
    if server_port < 1 or server_port > 65535:
        raise RuntimeConfigError("server.port must be in range [1, 65535]")

    policy_mode = str(raw.get("policy_mode", "custom")).strip().lower()
    if policy_mode not in {"strict", "balanced", "custom"}:
        raise RuntimeConfigError("policy_mode must be one of: strict, balanced, custom")

    try:
        timeout = float(raw.get("request_timeout_seconds", 60.0))
    except (TypeError, ValueError) as exc:
        raise RuntimeConfigError("request_timeout_seconds must be numeric") from exc
    if timeout <= 0:
        raise RuntimeConfigError("request_timeout_seconds must be > 0")

    prompt_logging_enabled = bool(logging_cfg.get("store_prompts", False))

    return RuntimeConfig(
        provider_name=provider_name,
        provider_model=provider_model,
        provider_base_url=provider_base_url,
        provider_api_key_env=provider_api_key_env,
        server_host=server_host,
        server_port=server_port,
        policy_mode=policy_mode,
        request_timeout_seconds=timeout,
        prompt_logging_enabled=prompt_logging_enabled,
    )


def runtime_config_to_dict(config: RuntimeConfig) -> Dict[str, Any]:
    return {
        "provider": {
            "name": config.provider_name,
            "model": config.provider_model,
            "base_url": config.provider_base_url,
            "api_key_env": config.provider_api_key_env,
        },
        "server": {
            "host": config.server_host,
            "port": config.server_port,
        },
        "policy_mode": config.policy_mode,
        "request_timeout_seconds": config.request_timeout_seconds,
        "logging": {
            "store_prompts": config.prompt_logging_enabled,
        },
    }


def save_runtime_config(config: RuntimeConfig, path: Path = CONFIG_PATH) -> None:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeConfigError(
            "PyYAML is required to write guardrail.config.yaml"
        ) from exc

    payload = runtime_config_to_dict(config)
    content = yaml.safe_dump(payload, sort_keys=False)
    path.write_text(content, encoding="utf-8")


def read_provider_api_key(config: RuntimeConfig) -> str:
    value = os.getenv(config.provider_api_key_env, "").strip()
    if not value:
        raise RuntimeConfigError(
            f"Provider API key missing. Set environment variable {config.provider_api_key_env}."
        )
    return value
