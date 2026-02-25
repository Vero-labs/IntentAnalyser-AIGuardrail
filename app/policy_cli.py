from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from app.services.classic_policy import (
    POLICY_PATH,
    ClassicPolicy,
    ClassicPolicyError,
    evaluate_classic_policy,
    load_classic_policy,
)
from app.services.runtime_config import (
    CONFIG_PATH,
    RuntimeConfig,
    RuntimeConfigError,
    default_runtime_config,
    load_runtime_config,
    save_runtime_config,
)
from app.wizard import InitWizardResult, run_init_wizard

DEFAULT_POLICY_CONTENT = """agent:
  name: recruiter-assistant

allowed_intents:
  - recruitment.question
  - candidate.screening
  - interview.scheduling

blocked_intents:
  - financial.advice
  - political.discussion
  - medical.advice

confidence:
  threshold: 0.6
  fallback: block

roles:
  admin:
    allow: ALL
  recruiter:
    allow:
      - recruitment.question
      - candidate.screening
"""


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ClassicPolicyError as exc:
        print(f"[ERR] {exc}")
        return 1
    except ValueError as exc:
        print(f"[ERR] {exc}")
        return 1
    except RuntimeError as exc:
        print(f"[ERR] {exc}")
        return 1
    except RuntimeConfigError as exc:
        print(f"[ERR] {exc}")
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guardrail",
        description="Classic Guardrail proxy with YAML policy enforcement",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Interactive setup wizard (policy + runtime config + .env).",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing policy/config/.env files.")
    init_parser.set_defaults(func=cmd_init)

    run_parser = subparsers.add_parser("run", help="Start guardrail proxy server.")
    run_parser.add_argument("--port", type=int, default=None, help="Server port (overrides config file)")
    run_parser.add_argument("--host", default=None, help="Server host (overrides config file)")
    run_parser.set_defaults(func=cmd_run)

    test_parser = subparsers.add_parser("test", help="Interactive local policy simulation.")
    test_parser.add_argument("--role", default="general", help="Role to test with")
    test_parser.add_argument(
        "--confidence",
        type=float,
        default=0.9,
        help="Confidence score used for local simulation [0..1]",
    )
    test_parser.set_defaults(func=cmd_test)

    policy_parser = subparsers.add_parser("policy", help="Policy inspection commands")
    policy_subparsers = policy_parser.add_subparsers(dest="policy_command", required=True)

    show_parser = policy_subparsers.add_parser("show", help="Display current policy summary")
    show_parser.set_defaults(func=cmd_policy_show)

    validate_parser = policy_subparsers.add_parser("validate", help="Validate policy YAML schema")
    validate_parser.set_defaults(func=cmd_policy_validate)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    policy_path = POLICY_PATH
    config_path = CONFIG_PATH
    env_path = Path(".env")
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    existing = [str(path) for path in (policy_path, config_path, env_path) if path.exists()]
    if existing and not args.force:
        print("[ERR] Refusing to overwrite existing files:")
        for path in existing:
            print(f"  - {path}")
        print("Use --force to overwrite.")
        return 1

    init_result = _build_init_result()
    policy_path.write_text(init_result.policy_yaml, encoding="utf-8")
    save_runtime_config(init_result.runtime_config, config_path)
    _write_env_file(env_path, init_result.env_vars)

    # The interactive wizard (Step 5) shows its own completion panel.
    # Only print plain output for non-interactive (piped) runs.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("[OK] Guardrail initialized")
        print(f"  - Policy: {policy_path}")
        print(f"  - Config: {config_path}")
        print(f"  - Env:    {env_path}")
    return 0


def cmd_policy_validate(args: argparse.Namespace) -> int:
    _ = args
    _load_or_exit()
    runtime_config = _load_runtime_or_exit()
    print(f"[OK] Policy is valid: {POLICY_PATH}")
    if CONFIG_PATH.exists():
        print(f"[OK] Runtime config is valid: {CONFIG_PATH}")
    else:
        print("[WARN] Runtime config file not found; using built-in defaults.")
        print(f"       Create {CONFIG_PATH} with 'guardrail init --force' for production.")
    print(f"[INFO] Active provider={runtime_config.provider_name} model={runtime_config.provider_model}")
    print(
        "[INFO] Active classifier="
        f"{runtime_config.classifier.mode} model={runtime_config.classifier.model} "
        f"offline_mode={runtime_config.classifier.offline_mode}"
    )
    return 0


def cmd_policy_show(args: argparse.Namespace) -> int:
    _ = args
    policy = _load_or_exit()
    runtime_config = _load_runtime_or_exit()
    _print_policy_summary(policy)
    print("Runtime config:")
    print(f"  provider={runtime_config.provider_name}")
    print(f"  model={runtime_config.provider_model}")
    print(f"  provider_base_url={runtime_config.provider_base_url}")
    print(f"  api_key_env={runtime_config.provider_api_key_env}")
    print(
        "  classifier="
        f"{runtime_config.classifier.mode}"
        f" (model={runtime_config.classifier.model}"
        f", offline_mode={runtime_config.classifier.offline_mode}"
        f", local_model_dir={runtime_config.classifier.local_model_dir or '-'}"
        ")"
    )
    print(f"  bind={runtime_config.server_host}:{runtime_config.server_port}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    policy = _load_or_exit()
    runtime_config = _load_runtime_or_exit()
    host = args.host or runtime_config.server_host
    port = int(args.port or runtime_config.server_port)
    endpoint_host = "localhost" if host in {"0.0.0.0", "::"} else host

    print("\n" + "=" * 60)
    print("[GUARDRAIL] Classic Policy Proxy")
    print("=" * 60)
    print(f"\n[ENDPOINT] Analyze endpoint: http://{endpoint_host}:{port}/intent")
    print(f"[PROXY] OpenAI proxy:       http://{endpoint_host}:{port}/proxy/openai/v1/chat/completions")
    print(f"[HEALTH] Health check:      http://{endpoint_host}:{port}/health")
    print(f"[DOCS] API docs:            http://{endpoint_host}:{port}/docs")
    print(f"[PROVIDER] Upstream:        {runtime_config.provider_base_url}")
    print(f"[MODEL] Default model:      {runtime_config.provider_model}")
    print(f"\n[POLICY] Agent: {policy.agent_name}")
    print(f"   Allowed intents: {len(policy.allowed_intents)}")
    print(f"   Blocked intents: {len(policy.blocked_intents)}")
    print(f"   Roles: {len(policy.roles)}")
    print("\n[CTRL] Press Ctrl+C to stop\n")
    print("=" * 60 + "\n")

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = str(host)

    try:
        subprocess.run([sys.executable, "-m", "app.main"], env=env, check=True)
    except KeyboardInterrupt:
        print("\n[STOP] Proxy stopped")
    except subprocess.CalledProcessError:
        print("\n[ERR] Proxy failed to start")
        return 1

    return 0


def cmd_test(args: argparse.Namespace) -> int:
    confidence = float(args.confidence)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("--confidence must be in [0, 1]")

    print("\n" + "=" * 60)
    print("[TEST] Classic Policy Simulation")
    print("=" * 60)
    print("Type prompts and see allow/block decisions from main.yaml")
    print("Policy is reloaded on every prompt (local simulation, no API call).")
    print("Press Ctrl+C to exit")
    print("=" * 60)

    try:
        while True:
            text = input("\n[INPUT] ").strip()
            if not text:
                continue

            policy = _load_or_exit()
            eval_result = evaluate_classic_policy(
                policy,
                role=args.role,
                detected_intent="unknown",
                confidence=confidence,
                text=text,
            )
            policy_intent = eval_result["policy_intent"]
            print("\n" + "-" * 60)
            print(f"Decision: {eval_result['decision'].upper()}")
            print(f"Intent:   {policy_intent}")
            print(f"Reason:   {eval_result['reason']}")
            print("-" * 60)
    except KeyboardInterrupt:
        print("\n\n[EXIT] Leaving test mode")

    return 0


def _load_or_exit() -> ClassicPolicy:
    if not POLICY_PATH.exists():
        raise ClassicPolicyError(
            f"Policy file not found: {POLICY_PATH}. Run 'guardrail init' first."
        )
    return load_classic_policy(POLICY_PATH)


def _load_runtime_or_exit() -> RuntimeConfig:
    if not CONFIG_PATH.exists():
        return default_runtime_config()
    return load_runtime_config(CONFIG_PATH)


def _build_init_result() -> InitWizardResult:
    if sys.stdin.isatty() and sys.stdout.isatty():
        return run_init_wizard()

    runtime_config = default_runtime_config()
    return InitWizardResult(
        policy_yaml=DEFAULT_POLICY_CONTENT,
        runtime_config=runtime_config,
        env_vars={
            runtime_config.provider_api_key_env: "",
        },
    )


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    """Merge *values* into an existing .env file, preserving other entries."""
    existing_lines: list[str] = []
    existing_keys: set[str] = set()

    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            # Parse KEY=VALUE lines (skip comments and blanks)
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    # Replace with new value
                    existing_lines.append(f"{key}={values[key]}")
                    existing_keys.add(key)
                else:
                    existing_lines.append(line)
            else:
                existing_lines.append(line)

    # Append any new keys that weren't already in the file
    new_keys = [k for k in values if k not in existing_keys]
    if new_keys:
        if existing_lines and existing_lines[-1].strip():
            existing_lines.append("")  # blank separator
        existing_lines.append("# Added by `guardrail init`")
        for key in new_keys:
            existing_lines.append(f"{key}={values[key]}")

    # If file didn't exist at all, add a header
    if not path.exists():
        header = [
            "# Guardrail environment variables",
            "# Generated by `guardrail init`",
            "",
        ]
        existing_lines = header + existing_lines

    existing_lines.append("")  # trailing newline
    path.write_text("\n".join(existing_lines), encoding="utf-8")


def _print_policy_summary(policy: ClassicPolicy) -> None:
    print(f"Policy file: {POLICY_PATH}")
    print(f"Agent: {policy.agent_name}")
    print("Allowed intents:")
    for intent in policy.allowed_intents:
        print(f"  - {intent}")
    print("Blocked intents:")
    for intent in policy.blocked_intents:
        print(f"  - {intent}")
    print("Confidence:")
    print(f"  threshold={policy.confidence_threshold}")
    print(f"  fallback={policy.confidence_fallback}")
    print("Roles:")
    if not policy.roles:
        print("  (none)")
        return
    for role_name, role_policy in sorted(policy.roles.items()):
        if role_policy.allow_all:
            print(f"  - {role_name}: ALL")
            continue
        allowed = ", ".join(role_policy.allowed_intents) if role_policy.allowed_intents else "(none)"
        blocked = ", ".join(role_policy.blocked_intents) if role_policy.blocked_intents else "(none)"
        print(f"  - {role_name}: allow={allowed} | block={blocked}")


if __name__ == "__main__":
    raise SystemExit(main())
