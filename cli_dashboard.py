import requests
import json
import sys
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

PROXY_URL = "http://localhost:8002/intent"
console = Console()

def send_prompt(prompt):
    payload = {"messages": [{"role": "user", "content": prompt}]}
    
    start_time = time.time()
    try:
        response = requests.post(PROXY_URL, json=payload, timeout=5)
        latency = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            return response.json(), latency, None
        else:
            return None, latency, f"Error {response.status_code}: {response.text}"
    except Exception as e:
        return None, 0, str(e)

def display_result(prompt, data, latency, error):
    console.print()
    if error:
        console.print(Panel(f"[bold red]Request Failed[/bold red]\n{error}", title="Error"))
        return

    # Extract key metrics
    intent = data.get("intent", "UNKNOWN")
    confidence = data.get("confidence", 0.0)
    risk_score = data.get("risk_score", 0.0)
    decision = data.get("decision", "allow")
    tier = data.get("tier", "N/A")
    breakdown = data.get("breakdown", {})

    # Determine styles
    decision_style = "green" if decision == "allow" else "bold red"
    risk_style = "green" if risk_score < 0.3 else ("yellow" if risk_score < 0.7 else "red")
    
    # Main Result Table
    table = Table(title=f"Analysis Result ({latency:.1f}ms)", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Decision", f"[{decision_style}]{decision.upper()}[/{decision_style}]")
    table.add_row("Intent", f"[bold]{intent}[/bold]")
    table.add_row("Confidence", f"{confidence:.2f}")
    table.add_row("Risk Score", f"[{risk_style}]{risk_score:.2f}[/{risk_style}]")
    table.add_row("Tier", tier)
    
    console.print(table)

    # Breakdown Table
    b_table = Table(title="Detector Breakdown", show_header=True, header_style="bold blue")
    b_table.add_column("Detector")
    b_table.add_column("Score/State")
    
    b_table.add_row("Regex Match", str(breakdown.get("regex_match", False)))
    b_table.add_row("Semantic Score", f"{breakdown.get('semantic_score', 0.0):.2f}")
    b_table.add_row("ZeroShot Score", f"{breakdown.get('zeroshot_score', 0.0):.2f}")
    
    console.print(b_table)
    console.print(Panel(f"[italic]{prompt}[/italic]", title="Original Prompt", border_style="dim"))

def main():
    console.print(Panel.fit("[bold cyan]Intent Analyzer CLI Dashboard[/bold cyan]\nType 'exit' to quit.", border_style="cyan"))
    
    while True:
        try:
            prompt = console.input("\n[bold green]Enter Prompt > [/bold green]")
            if prompt.strip().lower() in ["exit", "quit"]:
                console.print("[yellow]Exiting...[/yellow]")
                break
            
            if not prompt.strip():
                continue

            data, latency, error = send_prompt(prompt)
            display_result(prompt, data, latency, error)
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Exiting...[/yellow]")
            break

if __name__ == "__main__":
    main()
