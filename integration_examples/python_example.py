"""Guardrail Integration Example - Python"""
import requests

GUARDRAIL_URL = "http://localhost:8000/intent"

def check_input(user_text: str, role: str = "general") -> dict:
    """Check user input against guardrail"""
    response = requests.post(
        GUARDRAIL_URL,
        json={"text": user_text, "user_role": role},
        timeout=5
    )
    return response.json()

# Example usage
if __name__ == "__main__":
    result = check_input("Tell me about Python")
    
    if result["decision"] == "block":
        print(f"[BLOCKED] Blocked: {result['reason']}")
    else:
        print(f"[ALLOWED] Safe: {result['intent']}")
