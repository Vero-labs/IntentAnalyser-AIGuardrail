"""
High-Assurance Schemas — Hierarchical output contract.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.core.taxonomy import IntentCategory, IntentTier

class Message(BaseModel):
    role: str
    content: str


class IntentRequest(BaseModel):
    text: Optional[str] = None
    messages: Optional[List[Message]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class AnalysisBreakdown(BaseModel):
    """Component-level details for debugging and auditing."""
    regex_match: bool
    semantic_score: float
    zeroshot_score: float
    detected_tier: IntentTier


class IntentResponse(BaseModel):
    """
    Structured facts from the High-Assurance pipeline.
    
    Fields:
    - intent: The primary detected intent category.
    - confidence: How sure the system matches the intent (0.0-1.0).
    - risk_score: R_total calculated by the Risk Engine.
    - tier: The Priority Tier (P0-P4) this intent belongs to.
    - breakdown: Internal component scores.
    """
    intent: IntentCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    risk_score: float = Field(..., ge=0.0, le=1.0)
    tier: IntentTier
    breakdown: AnalysisBreakdown
    decision: str = "allow"
    reason: Optional[str] = None
    processing_time_ms: Optional[float] = None
    
    # Optional debug info
    trace: Optional[Dict[str, Any]] = None


class IntentResponseDebug(IntentResponse):
    """Same as IntentResponse, trace is already optional there."""
    pass
