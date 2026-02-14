import requests
import json
import time
import os
from rich.console import Console
from rich.table import Table
from rich.progress import track

# Target Proxy (agent-guardrail)
PROXY_URL = "http://localhost:8080/v1/chat/completions"
# Using a dummy model name, proxy should handle it
PAYLOAD_TEMPLATE = {
    "model": "gpt-3.5-turbo",
    "messages": []
}

console = Console()

def run_stress_test():
    dataset_path = os.path.join("tests", "dataset_200.json")
    if not os.path.exists(dataset_path):
        console.print(f"[bold red]Dataset not found at {dataset_path}[/bold red]")
        return

    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "categories": {}
    }
    
    for item in track(dataset, description="Running Proxy Stress Test..."):
        prompt = item["text"]
        expected = item["expected_decision"]
        category = item["category"]
        
        if category not in results["categories"]:
            results["categories"][category] = {"total": 0, "passed": 0, "failed": 0}
            
        payload = PAYLOAD_TEMPLATE.copy()
        payload["messages"] = [{"role": "user", "content": prompt}]
        
        try:
            start_time = time.time()
            response = requests.post(PROXY_URL, json=payload, timeout=5)
            latency = (time.time() - start_time) * 1000
            
            # Determine Actual Decision
            actual_decision = "allow"
            response_json = {}
            try:
                response_json = response.json()
            except:
                pass

            # Guardrail blocks always return 403 Forbidden
            if response.status_code == 403:
                 actual_decision = "block"
            # Also check for specific guardrail error codes if they leak into other statuses
            elif "error" in response_json:
                err = response_json.get("error", {})
                if isinstance(err, dict):
                    code = err.get("code", "")
                    if code in ["sidecar_blocked", "guardrail_blocked", "role_policy_blocked", "output_guardrail_blocked"]:
                        actual_decision = "block"
                elif isinstance(err, str): # specific case for simple error strings
                    if "blocked" in err.lower():
                        actual_decision = "block"
            
            # If status is 400/404/500 but NOT a guardrail block, it means it was forwarded and upstream failed
            # This counts as "allow" for our testing purposes (stress testing the guardrail)
            
            # Verify
            passed = (expected == actual_decision)
            
            results["total"] += 1
            results["categories"][category]["total"] += 1
            
            if passed:
                results["passed"] += 1
                results["categories"][category]["passed"] += 1
            else:
                results["failed"] += 1
                results["categories"][category]["failed"] += 1
                # Optional details for debugging failures
                if results["failed"] <= 5: # Only print first 5 failures
                     console.print(f"[red]FAIL[/red]: {category} | Exp: {expected} | Act: {actual_decision} | Msg: {prompt[:50]}...")

        except Exception as e:
            results["errors"] += 1
            console.print(f"[bold red]Request Error[/bold red]: {e}")
            
    # Summary
    console.print("\n[bold cyan]--- Proxy Stress Test Results ---[/bold cyan]")
    console.print(f"Total Requests: {results['total']}")
    console.print(f"Passed: [green]{results['passed']}[/green] ({results['passed']/results['total']*100:.1f}%)")
    console.print(f"Failed: [red]{results['failed']}[/red]")
    console.print(f"Errors: {results['errors']}")
    
    table = Table(title="Category Breakdown")
    table.add_column("Category", style="cyan")
    table.add_column("Total")
    table.add_column("Passed", style="green")
    table.add_column("Failed", style="red")
    table.add_column("Rate", style="bold")
    
    for cat, stats in results["categories"].items():
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        table.add_row(
            cat, 
            str(stats["total"]), 
            str(stats["passed"]), 
            str(stats["failed"]), 
            f"{rate:.1f}%"
        )
        
    console.print(table)
    
    # Save full results
    output_path = os.path.join("tests", "proxy_stress_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_stress_test()
