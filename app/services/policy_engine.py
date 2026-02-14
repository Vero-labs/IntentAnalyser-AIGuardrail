import logging
import cedarpy
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class EvaluationResult:
    decision: str
    reason: str
    diagnostics: List[str]

class PolicyEngine:
    def __init__(self, policy_path: str = "app/policies/main.cedar"):
        self.policy_path = policy_path
        try:
            with open(policy_path, "r") as f:
                self.policy_content = f.read()
            logger.info(f"Loaded Cedar policies from {policy_path}")
        except FileNotFoundError:
            logger.error(f"Policy file not found: {policy_path}")
            self.policy_content = ""

    def evaluate(
        self,
        principal: str,
        action: str,
        resource: str,
        context: Dict[str, Any]
    ) -> EvaluationResult:
        """
        Evaluate a request against the Cedar policies.
        """
        request = {
            "principal": principal,
            "action": action,
            "resource": resource,
            "context": context
        }
        
        # We assume empty entities list for now as our policies are self-contained
        # or rely on context. If we need hierarchical role checking that isn't
        # pure string matching, we'd populate entities here.
        entities = [] 

        try:
            result: cedarpy.AuthzResult = cedarpy.is_authorized(request, self.policy_content, entities)
            
            decision_str = "allow" if result.decision == cedarpy.Decision.Allow else "block"
            
            # Extract diagnostics (reasons for denial) if available
            reasons = []
            if hasattr(result, "diagnostics") and result.diagnostics:
                # Diagnostics object usually contains errors or reasons
                reasons = [str(d) for d in result.diagnostics.errors] if hasattr(result.diagnostics, "errors") else []

            # Add reason for blocking
            reason_msg = "Policy Check Passed"
            if decision_str == "block":
                reason_msg = f"Policy Denied: {', '.join(reasons) if reasons else 'Implicit Deny or Rule Block'}"

            return EvaluationResult(
                decision=decision_str,
                reason=reason_msg,
                diagnostics=reasons
            )

        except Exception as e:
            logger.error(f"Cedar Evaluation Error: {e}")
            return EvaluationResult(
                decision="block",
                reason=f"Evaluation Error: {str(e)}",
                diagnostics=[str(e)]
            )
