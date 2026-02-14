import time
from fastapi import Request, HTTPException
from app.core.cache import CacheService
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.limit = requests_per_minute
        self.window = 60  # seconds
        # We share the same CacheService instance (or create new, but Redis connection is pooled)
        self.cache = CacheService()
        
    async def __call__(self, request: Request):
        client_ip = request.client.host
        # Use a specific prefix for rate limiting keys
        key = f"rate_limit:{client_ip}"
        
        try:
            # Atomic increment with TTL
            # If key doesn't exist, it starts at 1.
            # If it exists, it increments.
            # TTL is set/refreshed on valid keys? 
            # Actually, standard pattern is:
            # - If key exists, incr.
            # - If not, set to 1 and expire.
            # My `increment` method handles this logic for both Redis and Memory.
            
            count = self.cache.increment(key, ttl_seconds=self.window)
            
            if count > self.limit:
                logger.warning(f"Rate limit exceeded for {client_ip}. Count: {count}")
                raise HTTPException(status_code=429, detail="Too Many Requests")
                
            # Add remaining limit header? (Optional, maybe later)
            
        except HTTPException:
            raise
        except Exception as e:
            # Fail open if cache errors to avoid blocking legit traffic during outage
            logger.error(f"Rate limiter error: {e}")
