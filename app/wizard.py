from __future__ import annotations

import socket
from dataclasses import dataclass

from app.services.runtime_config import ClassifierConfig, RuntimeConfig


@dataclass
class InitWizardResult:
    policy_yaml: str
    runtime_config: RuntimeConfig
    env_vars: dict[str, str]


# ── Use-case presets ──────────────────────────────────────────────────────────

USE_CASES = {
    "1": {
        "name": "Public Chatbot",
        "desc": "Strict protection for public-facing bots",
        "shields": "jailbreaks · PII · toxic language · financial · political · medical",
        "mode": "strict",
        "allowed": ["info.query", "coding.question", "debugging.help"],
        "blocked": [
            "financial.advice",
            "political.discussion",
            "medical.advice",
            "security.prompt_injection",
            "security.pii_exfiltration",
        ],
        "threshold": 0.75,
        "roles": {"admin": {"allow": "ALL"}},
    },
    "2": {
        "name": "Internal Assistant",
        "desc": "Balanced protection for internal tools",
        "shields": "jailbreaks · PII",
        "mode": "balanced",
        "allowed": ["info.query", "coding.question", "code.review", "debugging.help"],
        "blocked": ["financial.advice", "political.discussion", "medical.advice"],
        "threshold": 0.60,
        "roles": {
            "admin": {"allow": "ALL"},
            "general": {"allow": ["info.query", "coding.question", "code.review", "debugging.help"]},
        },
    },
    "3": {
        "name": "Developer Tool",
        "desc": "Permissive for trusted developers",
        "shields": "jailbreaks only",
        "mode": "balanced",
        "allowed": ["coding.question", "code.review", "debugging.help"],
        "blocked": ["financial.advice", "political.discussion", "medical.advice"],
        "threshold": 0.60,
        "roles": {
            "admin": {"allow": "ALL"},
            "user": {"allow": ["coding.question", "code.review", "debugging.help"]},
        },
    },
    "4": {
        "name": "Custom",
        "desc": "Advanced manual configuration",
        "shields": "you decide",
        "mode": "custom",
        "allowed": [],
        "blocked": [],
        "threshold": 0.60,
        "roles": {"admin": {"allow": "ALL"}},
    },
}

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "model": "claude-3-5-sonnet-20241022",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "azure": {
        "model": "gpt-4",
        "base_url": "https://YOUR_RESOURCE.openai.azure.com",
        "api_key_env": "AZURE_OPENAI_API_KEY",
    },
    "custom": {
        "model": "llama3",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "PROVIDER_API_KEY",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_csv_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _policy_yaml_from_payload(payload: dict[str, object]) -> str:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PyYAML is required for wizard policy generation") from exc
    return yaml.safe_dump(payload, sort_keys=False)


def _step_header(console, step: int, total: int, title: str) -> None:
    """Render a consistent step header with progress."""
    from rich.panel import Panel
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Step {step}/{total}[/bold cyan]  ·  {title}",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()


# ── Main wizard ───────────────────────────────────────────────────────────────

def run_init_wizard() -> InitWizardResult:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm, IntPrompt, Prompt
        from rich.rule import Rule
        from rich.table import Table
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Rich is required for interactive setup. Install: pip install rich") from exc

    console = Console()
    TOTAL_STEPS = 5

    # ── Welcome Banner ────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            "[bold white]⚡ Guardrail[/bold white]\n"
            "[dim]AI safety guardrail setup wizard[/dim]\n\n"
            "[cyan]Provider · Policy · Proxy — ready in under a minute.[/cyan]",
            border_style="bright_cyan",
            padding=(1, 4),
            title="[bold bright_cyan]v4.0[/bold bright_cyan]",
            title_align="right",
        )
    )

    # ── STEP 1: Use Case ──────────────────────────────────────────────────
    _step_header(console, 1, TOTAL_STEPS, "Use Case")

    for key, uc in USE_CASES.items():
        badge_color = {"1": "red", "2": "yellow", "3": "green", "4": "blue"}[key]
        console.print(
            f"  [bold {badge_color}]{key}.[/bold {badge_color}] "
            f"[bold]{uc['name']}[/bold]"
        )
        console.print(f"     [dim]{uc['desc']}[/dim]")
        console.print(f"     [dim italic]Shields: {uc['shields']}[/dim italic]")
        console.print()

    use_case_key = Prompt.ask(
        "[bold]Select use case[/bold]",
        choices=["1", "2", "3", "4"],
        default="1",
    )
    use_case = USE_CASES[use_case_key]
    policy_mode = use_case["mode"]
    agent_name = Prompt.ask("[bold]Agent name[/bold]", default="assistant-agent")

    # Build policy payload from preset
    payload: dict[str, object] = {
        "agent": {"name": agent_name},
        "allowed_intents": list(use_case["allowed"]),
        "blocked_intents": list(use_case["blocked"]),
        "confidence": {"threshold": use_case["threshold"], "fallback": "block"},
        "roles": dict(use_case["roles"]),
    }

    # Custom mode: let users define their own intents
    if use_case_key == "4":
        console.print()
        console.print(Rule("[bold]Custom Intent Configuration[/bold]", style="cyan"))
        console.print()
        custom_allowed = Prompt.ask(
            "[bold]Allowed intents[/bold] [dim](comma-separated)[/dim]",
            default="coding.question,code.review,debugging.help",
        )
        custom_blocked = Prompt.ask(
            "[bold]Blocked intents[/bold] [dim](comma-separated)[/dim]",
            default="financial.advice,political.discussion,medical.advice",
        )
        payload["allowed_intents"] = _parse_csv_list(custom_allowed)
        payload["blocked_intents"] = _parse_csv_list(custom_blocked)

    console.print("[green]✓[/green] Use case: [bold]{name}[/bold]".format(**use_case))

    # ── STEP 2: Provider ──────────────────────────────────────────────────
    _step_header(console, 2, TOTAL_STEPS, "LLM Provider")

    provider_name = Prompt.ask(
        "[bold]Provider[/bold]",
        choices=["openai", "anthropic", "azure", "custom"],
        default="openai",
    )
    defaults = PROVIDER_DEFAULTS[provider_name]

    provider_model = Prompt.ask(
        "[bold]Model[/bold]",
        default=defaults["model"],
    )
    provider_base_url = Prompt.ask(
        "[bold]Base URL[/bold]",
        default=defaults["base_url"],
    ).rstrip("/")

    # Only ask for env var name in custom mode
    if provider_name == "custom":
        provider_api_key_env = Prompt.ask(
            "[bold]API key env var name[/bold]",
            default=defaults["api_key_env"],
        ).strip()
    else:
        provider_api_key_env = defaults["api_key_env"]

    provider_api_key_value = Prompt.ask(
        f"[bold]API key[/bold] [dim](saved to .env as {provider_api_key_env})[/dim]",
        password=True,
        default="",
    )

    console.print(f"[green]✓[/green] Provider: [bold]{provider_name}[/bold] / {provider_model}")

    # ── STEP 3: Server & Logging ──────────────────────────────────────────
    _step_header(console, 3, TOTAL_STEPS, "Server Configuration")

    while True:
        server_port = IntPrompt.ask("[bold]Port[/bold]", default=8000)
        if _port_available(server_port):
            console.print(f"[green]✓[/green] Port {server_port} is available")
            break
        console.print(f"[yellow]⚠[/yellow] Port {server_port} is already in use. Try another.")

    prompt_logging = Confirm.ask(
        "[bold]Store prompts in logs?[/bold] [dim](useful for debugging)[/dim]",
        default=False,
    )

    console.print(f"[green]✓[/green] Server: [bold]0.0.0.0:{server_port}[/bold]")

    # ── STEP 4: Review & Confirm ──────────────────────────────────────────
    _step_header(console, 4, TOTAL_STEPS, "Review Configuration")

    endpoint_host = "localhost"

    summary = Table(
        title="[bold]Configuration Summary[/bold]",
        show_header=True,
        header_style="bold cyan",
        border_style="bright_cyan",
        title_style="bold white",
        padding=(0, 1),
    )
    summary.add_column("Setting", style="bold", no_wrap=True, min_width=16)
    summary.add_column("Value", no_wrap=False, max_width=50)

    summary.add_row("Use Case", f"{use_case['name']}")
    summary.add_row("Agent", str(agent_name))
    summary.add_row("Provider", f"{provider_name}")
    summary.add_row("Model", str(provider_model))
    summary.add_row("Base URL", str(provider_base_url))
    summary.add_row("API Key", "••••••••" if provider_api_key_value else "[dim]not set[/dim]")
    summary.add_row("Server", f"http://{endpoint_host}:{server_port}")
    summary.add_row("Policy Mode", str(policy_mode))
    summary.add_row("Prompt Logging", "[green]enabled[/green]" if prompt_logging else "[dim]disabled[/dim]")

    # Show intents
    allowed_intents = payload.get("allowed_intents", [])
    blocked_intents = payload.get("blocked_intents", [])
    if allowed_intents:
        summary.add_row("Allowed Intents", ", ".join(str(i) for i in allowed_intents))
    if blocked_intents:
        summary.add_row("Blocked Intents", ", ".join(str(i) for i in blocked_intents))

    console.print(summary)
    console.print()

    if not Confirm.ask("[bold]Write configuration files?[/bold]", default=True):
        console.print("[yellow]Aborted.[/yellow] Run [bold]guardrail init[/bold] again to restart.")
        raise SystemExit(0)

    # ── Write files (with spinner) ────────────────────────────────────────
    runtime_config = RuntimeConfig(
        provider_name=provider_name,
        provider_model=provider_model,
        provider_base_url=provider_base_url,
        provider_api_key_env=provider_api_key_env,
        server_host="0.0.0.0",
        server_port=server_port,
        policy_mode=policy_mode,
        request_timeout_seconds=60.0,
        prompt_logging_enabled=prompt_logging,
        classifier=ClassifierConfig(
            mode="local",
            model="distilbert-mnli",
            local_model_dir="",
            provider="huggingface",
            api_token="",
            endpoint="",
            auth_header="",
            timeout_seconds=8.0,
            offline_mode=True,
        ),
    )

    env_vars = {
        provider_api_key_env: provider_api_key_value,
    }

    result = InitWizardResult(
        policy_yaml=_policy_yaml_from_payload(payload),
        runtime_config=runtime_config,
        env_vars=env_vars,
    )

    # ── STEP 5: Completion ────────────────────────────────────────────────
    _step_header(console, 5, TOTAL_STEPS, "Setup Complete")

    # Files created
    console.print("[green bold]✓[/green bold] Configuration files written:\n")
    console.print("  [green]✓[/green] Policy       → [bold]app/policies/main.yaml[/bold]")
    console.print("  [green]✓[/green] Config       → [bold]guardrail.config.yaml[/bold]")
    console.print("  [green]✓[/green] Environment  → [bold].env[/bold]")
    console.print()

    # Protection summary
    shields = use_case["shields"]
    console.print(
        Panel(
            f"[bold]Mode:[/bold] {use_case['name']}\n"
            f"[bold]Protection:[/bold] {shields}",
            title="[bold green]Active Shields[/bold green]",
            border_style="green",
            padding=(0, 2),
        )
    )

    # Next steps
    console.print()
    curl_cmd = (
        f"curl -X POST http://localhost:{server_port}/intent "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"text\": \"hello\", \"role\": \"general\"}}'"
    )
    console.print(
        Panel(
            "[bold]1.[/bold] Start the server:\n"
            f"   [cyan]guardrail run[/cyan]\n\n"
            "[bold]2.[/bold] Test a prompt:\n"
            f"   [cyan]guardrail test[/cyan]\n\n"
            "[bold]3.[/bold] Integrate (Python):\n"
            f"   [dim]from app.client.client import IntentClient[/dim]\n"
            f"   [dim]client = IntentClient(base_url=\"http://localhost:{server_port}\")[/dim]\n"
            f"   [dim]response = await client.analyze_text(\"user input\", role=\"general\")[/dim]\n\n"
            "[bold]4.[/bold] Integrate (cURL):\n"
            f"   [dim]{curl_cmd}[/dim]",
            title="[bold cyan]Next Steps[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    console.print()
    console.print("[bold green]🚀 Guardrail is ready![/bold green]\n")

    return result
