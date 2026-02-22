from __future__ import annotations

import argparse
import os
import subprocess
import sys

from app.services.classic_policy import (
    ClassicPolicy,
    ClassicPolicyError,
    POLICY_PATH,
    evaluate_classic_policy,
    load_classic_policy,
)

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guardrail",
        description="Classic Guardrail proxy with YAML policy enforcement",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a starter app/policies/main.yaml policy file.")
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing policy file.")
    init_parser.set_defaults(func=cmd_init)

    run_parser = subparsers.add_parser("run", help="Start guardrail proxy server.")
    run_parser.add_argument("--port", type=int, default=8000, help="Server port")
    run_parser.add_argument("--host", default="localhost", help="Server host")
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
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    if policy_path.exists() and not args.force:
        print(f"[ERR] Policy already exists at {policy_path}. Use --force to overwrite.")
        return 1

    policy_path.write_text(DEFAULT_POLICY_CONTENT, encoding="utf-8")
    print(f"[OK] Policy initialized: {policy_path}")
    return 0


def cmd_policy_validate(args: argparse.Namespace) -> int:
    _ = args
    _load_or_exit()
    print(f"[OK] Policy is valid: {POLICY_PATH}")
    return 0


def cmd_policy_show(args: argparse.Namespace) -> int:
    _ = args
    policy = _load_or_exit()
    _print_policy_summary(policy)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    policy = _load_or_exit()

    print("\n" + "=" * 60)
    print("[GUARDRAIL] Classic Policy Proxy")
    print("=" * 60)
    print(f"\n[ENDPOINT] Analyze endpoint: http://{args.host}:{args.port}/intent")
    print(f"[HEALTH] Health check:      http://{args.host}:{args.port}/health")
    print(f"[DOCS] API docs:            http://{args.host}:{args.port}/docs")
    print(f"\n[POLICY] Agent: {policy.agent_name}")
    print(f"   Allowed intents: {len(policy.allowed_intents)}")
    print(f"   Blocked intents: {len(policy.blocked_intents)}")
    print(f"   Roles: {len(policy.roles)}")
    print("\n[CTRL] Press Ctrl+C to stop\n")
    print("=" * 60 + "\n")

    env = os.environ.copy()
    env["PORT"] = str(args.port)
    env["HOST"] = str(args.host)

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
            f"Policy file not found: {POLICY_PATH}. Run './guardrail init' first."
        )
    return load_classic_policy(POLICY_PATH)


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
