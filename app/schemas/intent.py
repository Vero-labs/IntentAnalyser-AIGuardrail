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
    regex_match: bool = False
    semantic_score: float = 0.0
    zeroshot_score: float = 0.0
    detected_tier: IntentTier

class IntentResponse(BaseModel):
    intent: IntentCategory
    confidence: float
    risk_score: float = Field(..., description="Normalized risk score from 0.0 to 1.0")
    tier: IntentTier
    breakdown: Optional[AnalysisBreakdown] = None
    processing_time_ms: float = 0.0
