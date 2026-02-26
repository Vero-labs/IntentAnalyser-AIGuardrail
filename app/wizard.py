from __future__ import annotations

import socket
from dataclasses import dataclass

from app.services.runtime_config import ClassifierConfig, RuntimeConfig


@dataclass
class InitWizardResult:
    policy_yaml: str
    runtime_config: RuntimeConfig
    env_vars: dict[str, str]


# ── Color Palette ─────────────────────────────────────────────────────────────
# Accent: cyan / bright_cyan  — borders, highlights, active elements
# Base:   white / dim          — body text, descriptions
# Ok:     green                — success, checkmarks
# Warn:   yellow               — warnings

ACCENT = "cyan"
ACCENT_BRIGHT = "bright_cyan"
DIM = "dim"
OK = "green"
WARN = "yellow"

# ── Questionary style (accent + base) ────────────────────────────────────────
_QS_STYLE = None  # lazy-loaded


def _questionary_style():
    global _QS_STYLE
    if _QS_STYLE is None:
        from questionary import Style
        _QS_STYLE = Style([
            ("qmark", "fg:cyan bold"),           # ? marker
            ("question", "bold"),                 # prompt text
            ("pointer", "fg:cyan bold"),          # ▸ pointer (accent)
            ("highlighted", ""),                  # focused item text (no highlight)
            ("selected", "fg:cyan"),              # ● selected checkbox marker
            ("separator", "fg:#808080"),          # separator lines
            ("instruction", "fg:#808080"),        # (Use arrows)
            ("text", ""),                         # default text
            ("answer", "fg:cyan bold"),           # submitted answer
        ])
    return _QS_STYLE


# ── Use-case presets ──────────────────────────────────────────────────────────

USE_CASES = {
    "1": {
        "name": "Public Chatbot",
        "desc": "Strict protection for public-facing bots",
        "shields": "jailbreaks | PII | toxic language | financial | political | medical",
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
        "shields": "jailbreaks | PII",
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


def _progress_bar(step: int, total: int) -> str:
    """Render a text-based progress track: ━━━●━━━━━━━."""
    filled = "━" * (step - 1)
    remaining = "━" * (total - step)
    return f"[{ACCENT}]{filled}[/{ACCENT}][bold {ACCENT_BRIGHT}]●[/bold {ACCENT_BRIGHT}][{DIM}]{remaining}[/{DIM}]"


def _step_header(console, step: int, total: int, title: str) -> None:
    """Render a consistent step header with a progress track."""
    from rich.text import Text

    console.print()
    bar = _progress_bar(step, total)
    console.print(
        f"  {bar}  [{ACCENT}]Step {step}/{total}[/{ACCENT}]  │  "
        f"[bold white]{title}[/bold white]"
    )
    console.print(f"  [{DIM}]{'─' * 44}[/{DIM}]")
    console.print()


# ── Main wizard ───────────────────────────────────────────────────────────────

def run_init_wizard() -> InitWizardResult:
    try:
        import questionary
        from questionary import Choice
        from rich.console import Console
        from rich.panel import Panel
        from rich.prompt import Confirm, IntPrompt, Prompt
        from rich.rule import Rule
        from rich.table import Table
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Rich and questionary are required for interactive setup. "
            "Install: pip install rich questionary"
        ) from exc

    console = Console()
    style = _questionary_style()
    TOTAL_STEPS = 5

    # ── Welcome Banner ────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            f"[bold {ACCENT_BRIGHT}]›[/bold {ACCENT_BRIGHT}] "
            f"[bold white]Guardrail[/bold white]  "
            f"[{DIM}]AI Safety Guardrail[/{DIM}]\n"
            f"\n"
            f"  [{DIM}]Configure your provider, policy, and proxy[/{DIM}]\n"
            f"  [{DIM}]in a few quick steps.[/{DIM}]",
            border_style=ACCENT,
            padding=(1, 3),
            title=f"[bold {ACCENT_BRIGHT}] v4.0 [/bold {ACCENT_BRIGHT}]",
            title_align="right",
            subtitle=f"[{DIM}] Setup Wizard [/{DIM}]",
            subtitle_align="left",
        )
    )

    # ── STEP 1: Use Case ──────────────────────────────────────────────────
    _step_header(console, 1, TOTAL_STEPS, "Use Case")

    # Build questionary select choices for use cases
    uc_choices = []
    for key, uc in USE_CASES.items():
        label = f"{uc['name']:20s} {uc['desc']}"
        uc_choices.append(Choice(title=label, value=key))

    use_case_key = questionary.select(
        "Select a use case:",
        choices=uc_choices,
        default="1",
        style=style,
        qmark="›",
        pointer="▸",
        instruction="(↑/↓ navigate, Enter select)",
    ).ask()

    if use_case_key is None:
        console.print(f"[{WARN}]Aborted.[/{WARN}]")
        raise SystemExit(1)

    use_case = USE_CASES[use_case_key]
    policy_mode = use_case["mode"]

    # Show selected use case shields
    console.print(
        f"  [{DIM}]Shields:[/{DIM}] [{ACCENT}]{use_case['shields']}[/{ACCENT}]"
    )
    console.print()

    agent_name = Prompt.ask(
        f"  [{ACCENT}]›[/{ACCENT}] [bold]Agent name[/bold]",
        default="assistant-agent",
    )

    # Build policy payload from preset
    payload: dict[str, object] = {
        "agent": {"name": agent_name},
        "allowed_intents": list(use_case["allowed"]),
        "blocked_intents": list(use_case["blocked"]),
        "confidence": {"threshold": use_case["threshold"], "fallback": "block"},
        "roles": dict(use_case["roles"]),
    }

    # Custom mode: let users pick intents interactively
    if use_case_key == "4":
        from app.core.taxonomy import INTENT_DESCRIPTIONS, TIER_MAPPING, IntentCategory

        console.print()
        console.print(
            f"  [{DIM}]{'─' * 44}[/{DIM}]"
        )
        console.print(
            f"  [{ACCENT}]›[/{ACCENT}] [bold]Custom Intent Configuration[/bold]"
        )
        console.print(
            f"  [{DIM}]Use ↑/↓ to navigate, Space to toggle, Enter to confirm[/{DIM}]"
        )
        console.print()

        intents_list = list(IntentCategory)
        # Build checkbox choices with tier tag, intent name, and short description
        choices: list[Choice] = []
        # Pre-select benign P4 intents by default
        default_allowed = {"info.query", "info.summarize", "tool.safe", "conv.greeting"}

        for intent in intents_list:
            tier = str(TIER_MAPPING.get(intent, "")).split(".")[-1]
            desc = INTENT_DESCRIPTIONS.get(intent, "")
            if len(desc) > 50:
                desc = desc[:47] + "..."
            label = f"[{tier}] {intent.value:24s} {desc}"
            choices.append(
                Choice(
                    title=label,
                    value=intent.value,
                    checked=intent.value in default_allowed,
                )
            )

        selected_values = questionary.checkbox(
            "Select intents to ALLOW (everything else will be BLOCKED):",
            choices=choices,
            style=style,
            qmark="›",
            pointer="▸",
            instruction="(↑/↓ navigate, Space toggle, Enter confirm)",
        ).ask()

        if selected_values is None:
            console.print(f"[{WARN}]Aborted.[/{WARN}]")
            raise SystemExit(1)

        allowed_intents = list(selected_values)
        blocked_intents = [
            cat.value for cat in intents_list if cat.value not in allowed_intents
        ]

        payload["allowed_intents"] = allowed_intents
        payload["blocked_intents"] = blocked_intents

        console.print()
        console.print(
            f"  [{OK}]●[/{OK}] Allowed: [{ACCENT}]{', '.join(allowed_intents) or 'none'}[/{ACCENT}]"
        )
        console.print(
            f"  [{WARN}]●[/{WARN}] Blocked: [{DIM}]{', '.join(blocked_intents) or 'none'}[/{DIM}]"
        )

    console.print(
        f"\n  [{OK}]✓[/{OK}] Use case: [bold]{use_case['name']}[/bold]"
    )

    # ── STEP 2: Provider ──────────────────────────────────────────────────
    _step_header(console, 2, TOTAL_STEPS, "LLM Provider")

    # Provider selection with questionary
    provider_choices = [
        Choice(title=f"{'OpenAI':16s} GPT-4o-mini, GPT-4", value="openai"),
        Choice(title=f"{'Anthropic':16s} Claude 3.5 Sonnet", value="anthropic"),
        Choice(title=f"{'Azure OpenAI':16s} GPT-4 on Azure", value="azure"),
        Choice(title=f"{'Custom':16s} Self-hosted / other", value="custom"),
    ]

    provider_name = questionary.select(
        "Select LLM provider:",
        choices=provider_choices,
        default="openai",
        style=style,
        qmark="›",
        pointer="▸",
        instruction="(↑/↓ navigate, Enter select)",
    ).ask()

    if provider_name is None:
        console.print(f"[{WARN}]Aborted.[/{WARN}]")
        raise SystemExit(1)

    defaults = PROVIDER_DEFAULTS[provider_name]

    console.print()
    provider_model = Prompt.ask(
        f"  [{ACCENT}]›[/{ACCENT}] [bold]Model[/bold]",
        default=defaults["model"],
    )
    provider_base_url = Prompt.ask(
        f"  [{ACCENT}]›[/{ACCENT}] [bold]Base URL[/bold]",
        default=defaults["base_url"],
    ).rstrip("/")

    # Only ask for env var name in custom mode
    if provider_name == "custom":
        provider_api_key_env = Prompt.ask(
            f"  [{ACCENT}]›[/{ACCENT}] [bold]API key env var name[/bold]",
            default=defaults["api_key_env"],
        ).strip()
    else:
        provider_api_key_env = defaults["api_key_env"]

    provider_api_key_value = Prompt.ask(
        f"  [{ACCENT}]›[/{ACCENT}] [bold]API key[/bold] [{DIM}](saved to .env as {provider_api_key_env})[/{DIM}]",
        password=True,
        default="",
    )

    console.print(
        f"\n  [{OK}]✓[/{OK}] Provider: [bold]{provider_name}[/bold] / {provider_model}"
    )

    # ── STEP 3: Server & Logging ──────────────────────────────────────────
    _step_header(console, 3, TOTAL_STEPS, "Server Configuration")

    while True:
        server_port = IntPrompt.ask(
            f"  [{ACCENT}]›[/{ACCENT}] [bold]Port[/bold]",
            default=8000,
        )
        if _port_available(server_port):
            console.print(
                f"  [{OK}]✓[/{OK}] Port {server_port} is available"
            )
            break
        console.print(
            f"  [{WARN}]![/{WARN}] Port {server_port} is already in use. Try another."
        )

    console.print()

    # Prompt logging with questionary select
    log_choice = questionary.select(
        "Store prompts in logs? (useful for debugging)",
        choices=[
            Choice(title="No   — prompts are not stored", value=False),
            Choice(title="Yes  — store prompts for debugging", value=True),
        ],
        default=False,
        style=style,
        qmark="›",
        pointer="▸",
    ).ask()

    if log_choice is None:
        console.print(f"[{WARN}]Aborted.[/{WARN}]")
        raise SystemExit(1)

    prompt_logging = log_choice

    console.print(
        f"\n  [{OK}]✓[/{OK}] Server: [bold]0.0.0.0:{server_port}[/bold]"
    )

    # ── STEP 4: Review & Confirm ──────────────────────────────────────────
    _step_header(console, 4, TOTAL_STEPS, "Review Configuration")

    endpoint_host = "localhost"

    summary = Table(
        show_header=True,
        header_style=f"bold {ACCENT}",
        border_style=ACCENT,
        padding=(0, 2),
        show_lines=True,
    )
    summary.add_column("Setting", style="bold white", no_wrap=True, min_width=18)
    summary.add_column("Value", style=f"{ACCENT}", no_wrap=False, max_width=50)

    summary.add_row("Use Case", f"{use_case['name']}")
    summary.add_row("Agent", str(agent_name))
    summary.add_row("Provider", f"{provider_name}")
    summary.add_row("Model", str(provider_model))
    summary.add_row("Base URL", str(provider_base_url))
    summary.add_row(
        "API Key",
        f"[{OK}]●[/{OK}] set" if provider_api_key_value else f"[{DIM}]○ not set[/{DIM}]",
    )
    summary.add_row("Server", f"http://{endpoint_host}:{server_port}")
    summary.add_row("Policy Mode", str(policy_mode))
    summary.add_row(
        "Prompt Logging",
        f"[{OK}]● enabled[/{OK}]" if prompt_logging else f"[{DIM}]○ disabled[/{DIM}]",
    )

    # Show intents
    allowed_intents_list = payload.get("allowed_intents", [])
    blocked_intents_list = payload.get("blocked_intents", [])
    if allowed_intents_list:
        summary.add_row("Allowed Intents", ", ".join(str(i) for i in allowed_intents_list))
    if blocked_intents_list:
        summary.add_row("Blocked Intents", ", ".join(str(i) for i in blocked_intents_list))

    console.print(summary)
    console.print()

    # Confirm with questionary
    confirm = questionary.confirm(
        "Write configuration files?",
        default=True,
        style=style,
        qmark="›",
    ).ask()

    if not confirm:
        console.print(
            f"[{WARN}]Aborted.[/{WARN}] Run [bold]guardrail init[/bold] again to restart."
        )
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
    console.print(
        Panel(
            f"  [{OK}]✓[/{OK}] Policy       → [bold]app/policies/main.yaml[/bold]\n"
            f"  [{OK}]✓[/{OK}] Config       → [bold]guardrail.config.yaml[/bold]\n"
            f"  [{OK}]✓[/{OK}] Environment  → [bold].env[/bold]",
            border_style=OK,
            title=f"[bold {OK}] Files Written [/bold {OK}]",
            padding=(1, 2),
        )
    )

    # Protection summary
    shields = use_case["shields"]
    console.print(
        Panel(
            f"  [bold]Mode:[/bold]       [{ACCENT}]{use_case['name']}[/{ACCENT}]\n"
            f"  [bold]Protection:[/bold] [{ACCENT}]{shields}[/{ACCENT}]",
            title=f"[bold {ACCENT_BRIGHT}] Active Shields [/bold {ACCENT_BRIGHT}]",
            border_style=ACCENT,
            padding=(1, 2),
        )
    )

    # Next steps
    curl_cmd = (
        f"curl -X POST http://localhost:{server_port}/intent "
        f"-H 'Content-Type: application/json' "
        f"-d '{{\"text\": \"hello\", \"role\": \"general\"}}'"
    )
    console.print(
        Panel(
            f"  [bold]1.[/bold] Start the server\n"
            f"     [{ACCENT}]$ guardrail run[/{ACCENT}]\n"
            f"\n"
            f"  [bold]2.[/bold] Test a prompt\n"
            f"     [{ACCENT}]$ guardrail test[/{ACCENT}]\n"
            f"\n"
            f"  [bold]3.[/bold] Integrate (Python)\n"
            f"     [{DIM}]from app.client.client import IntentClient[/{DIM}]\n"
            f"     [{DIM}]client = IntentClient(base_url=\"http://localhost:{server_port}\")[/{DIM}]\n"
            f"     [{DIM}]response = await client.analyze_text(\"user input\", role=\"general\")[/{DIM}]\n"
            f"\n"
            f"  [bold]4.[/bold] Integrate (cURL)\n"
            f"     [{DIM}]{curl_cmd}[/{DIM}]",
            title=f"[bold {ACCENT_BRIGHT}] Next Steps [/bold {ACCENT_BRIGHT}]",
            border_style=ACCENT,
            padding=(1, 2),
        )
    )

    console.print()
    console.print(
        f"  [{OK}]✓[/{OK}] [bold {OK}]Guardrail is ready![/bold {OK}]"
    )
    console.print()

    return result
