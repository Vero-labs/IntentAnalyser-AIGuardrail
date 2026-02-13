import httpx
import json
import os

INTENT_URL = "http://localhost:8002/intent"
TEST_FILE = "tests/tests.json"

def run_tests():
    with open(TEST_FILE, "r") as f:
        tests = json.load(f)
    
    test_cases = tests["test_cases"]
    passed = 0
    failed = 0
    false_negatives = 0
    
    print(f"=== Running {len(test_cases)} Test Cases ===\n")
    
    with httpx.Client(timeout=30.0) as client:
        for test in test_cases:
            test_id = test["id"]
            input_text = test["input"]
            expected = test["expected_intent"]
            
            try:
                resp = client.post(INTENT_URL, json={"text": input_text})
                if resp.status_code != 200:
                    print(f"[{test_id}] ❌ ERROR: Status {resp.status_code}")
                    failed += 1
                    continue
                
                data = resp.json()
                actual = data["intent"]
                confidence = data.get("confidence", 0)
                
                if actual == expected:
                    status = "✅ PASS"
                    passed += 1
                else:
                    status = "❌ FAIL"
                    failed += 1
                    
                    # False negative logic from bash script
                    safe_intents = ["info.query", "info.summarize", "conv.greeting", "conv.other", "tool.safe", "unknown"]
                    is_expected_risky = expected not in safe_intents
                    is_actual_safe = actual in safe_intents
                    
                    if is_expected_risky and is_actual_safe:
                        status = "🔴 FALSE NEGATIVE"
                        false_negatives += 1
                
                print(f"[{test_id}] {status} | Intent: {actual} (exp: {expected}) | Confidence: {confidence:.3f}")
                
            except Exception as e:
                print(f"[{test_id}] ❌ EXCEPTION: {e}")
                failed += 1

    print(f"\n=== Summary ===")
    print(f"Total:           {len(test_cases)}")
    print(f"Passed:          {passed}")
    print(f"Failed:          {failed}")
    print(f"False Negatives: {false_negatives}")

if __name__ == "__main__":
    run_tests()
