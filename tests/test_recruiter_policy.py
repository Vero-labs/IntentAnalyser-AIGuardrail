import time

import requests

BASE_URL = "http://localhost:8002/intent"

def test_recruiter_policy():
    # Helper to send request
    def check(text, role, expected_decision, description):
        payload = {
            "text": text,
            "user_role": role
        }
        try:
            response = requests.post(BASE_URL, json=payload, timeout=5)
            data = response.json()
            decision = data.get("decision", "unknown")
            print(f"[{'PASS' if decision == expected_decision else 'FAIL'}] {description}")
            print(f"   Input: '{text}' | Role: {role}")
            print(f"   Expected: {expected_decision} | Got: {decision}")
            if decision != expected_decision:
                print(f"   Reason: {data.get('reason')}")
                print(f"   Domain: {data.get('trace', {}).get('policy', {}).get('context', {}).get('domain')}")
        except Exception as e:
            print(f"[ERROR] {description}: {e}")

    print("--- Verifying Recruiter Policy ---")

    # Wait for server
    time.sleep(2)

    # Case 1: Recruiter asking about recruitment (Should Allow)
    check(
        "Schedule an interview with the candidate",
        "recruiter",
        "allow",
        "Recruiter: Recruitment Query"
    )

    # Case 2: Recruiter saying Hello (Should Allow via global greet allow)
    check(
        "Hello there",
        "recruiter",
        "allow",
        "Recruiter: Greeting"
    )

    # Case 3: Recruiter asking random question (Should Block)
    # "Who is Jack?" -> Domain: general_knowledge -> Recruiter only allows 'recruitment'
    check(
        "Who is Jack?",
        "recruiter",
        "block",
        "Recruiter: Random Question (Who is Jack?)"
    )

    # Case 4: General user asking random question (Should Allow)
    check(
        "Who is Jack?",
        "general",
        "allow",
        "General: Random Question (Who is Jack?)"
    )

    # Case 5: Recruiter asking for Python code (Should Block - domain technical)
    check(
        "Write a python script",
        "recruiter",
        "block",
        "Recruiter: Code Generation"
    )

if __name__ == "__main__":
    test_recruiter_policy()
