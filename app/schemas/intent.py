"""
Tri-Axis Schemas — Flat output contract.

The analyzer emits structured facts. No nesting. No noise.
Trace/observability is available via ?debug=true query param.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from app.core.axes import Action, Domain, RiskSignal


class Message(BaseModel):
    role: str
    content: str


class IntentRequest(BaseModel):
    text: Optional[str] = None
    messages: Optional[List[Message]] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class IntentResponse(BaseModel):
    """Flat, structured facts from the tri-axis pipeline."""
    action: Action
    action_confidence: float = Field(..., ge=0.0, le=1.0)
    domain: Domain
    domain_confidence: float = Field(..., ge=0.0, le=1.0)
    risk_signals: List[RiskSignal] = [RiskSignal.NONE]
    risk_score: float = Field(0.0, ge=0.0, le=1.0)
    ambiguity: bool = False
    processing_time_ms: Optional[float] = None


class DetectorTrace(BaseModel):
    """Full observability trace. Only included when ?debug=true."""
    regex_triggered: bool = False
    regex_signals: List[str] = []
    risk_semantic_scores: Dict[str, float] = {}
    risk_detection_path: str = ""
    action_all_scores: Dict[str, float] = {}
    domain_all_scores: Dict[str, float] = {}
    dominant_layer: str = ""
    pipeline_short_circuited: bool = False


class IntentResponseDebug(IntentResponse):
    """Extended response with trace — only via ?debug=true."""
    trace: Optional[DetectorTrace] = None
