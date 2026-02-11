import httpx
from typing import Optional, List, Dict, Any
from app.schemas.intent import IntentRequest, IntentResponse

class IntentClient:
    def __init__(self, base_url: str = "http://localhost:8002", timeout: float = 5.0):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def close(self):
        await self.client.aclose()

    async def analyze_text(self, text: str, user_id: Optional[str] = None) -> IntentResponse:
        """
        Analyze a simple text string.
        """
        payload = {"text": text, "user_id": user_id}
        response = await self.client.post("/intent", json=payload)
        response.raise_for_status()
        return IntentResponse(**response.json())

    async def analyze_chat(self, messages: List[Dict[str, str]], user_id: Optional[str] = None) -> IntentResponse:
        """
        Analyze a conversation history.
        messages should be a list of dicts: [{"role": "user", "content": "..."}]
        """
        payload = {"messages": messages, "user_id": user_id}
        response = await self.client.post("/intent", json=payload)
        response.raise_for_status()
        return IntentResponse(**response.json())
