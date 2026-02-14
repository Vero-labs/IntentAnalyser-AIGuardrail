import logging
import json
import hashlib
from typing import Optional, Dict, Any, Union
import time

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis = None
        self.memory_cache = {}
        self.max_memory_size = 1000
        
        try:
            import redis
            # Short timeout to fail fast if Redis isn't running
            self.redis = redis.from_url(redis_url, socket_timeout=0.5)
            self.redis.ping()
            logger.info("✅ Connected to Redis Cache.")
        except Exception:
            logger.warning("⚠️ Redis unavailable (Connection Refused). Falling back to In-Memory Cache.")
            self.redis = None
        
        self.counters = {}

    def _hash_key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def get(self, text: str) -> Optional[Dict[str, Any]]:
        key = self._hash_key(text)
        
        # 1. Try Redis
        if self.redis:
            try:
                val = self.redis.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.error(f"Redis Read Error: {e}")
        
        # 2. Try Memory (Fallback)
        return self.memory_cache.get(key)

    def set(self, text: str, data: Dict[str, Any], ttl_seconds: int = 3600):
        key = self._hash_key(text)
        
        # 1. Write to Redis
        if self.redis:
            try:
                self.redis.setex(key, ttl_seconds, json.dumps(data))
            except Exception as e:
                logger.error(f"Redis Write Error: {e}")
        
        # 2. Write to Memory (Always, as tier 1 or fallback)
        self._prune_memory()
        self.memory_cache[key] = data

    def increment(self, key: str, ttl_seconds: int = 60) -> int:
        """Atomic increment for rate limiting."""
        # 1. Redis
        if self.redis:
            try:
                # Pipeline for atomicity (mostly)
                pipe = self.redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl_seconds)
                result = pipe.execute()
                return result[0] # Returns the new value
            except Exception as e:
                logger.error(f"Redis Increment Error: {e}")
                # Fallthrough to memory
        
        # 2. Memory
        # Check expiry logic for memory counters (simplified)
        now = int(time.time())
        if key not in self.counters:
            self.counters[key] = {"count": 1, "expires_at": now + ttl_seconds}
            return 1
        
        data = self.counters[key]
        if now > data["expires_at"]:
            # Expired, reset
            self.counters[key] = {"count": 1, "expires_at": now + ttl_seconds}
            return 1
        
        # Increment
        data["count"] += 1
        return data["count"]

    def _prune_memory(self):
        """Simple FIFO prune if size exceeds limit."""
        if len(self.memory_cache) > self.max_memory_size:
            # Remove first inserted item (naive)
            first_key = next(iter(self.memory_cache))
            del self.memory_cache[first_key]
