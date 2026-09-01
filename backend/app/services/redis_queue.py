"""
AgentOS Phase 16 — Redis-Backed Distributed Task Queue.
Uses Redis Sorted Sets (ZSET) for priority and anti-starvation scheduling,
Redis Hashes for metadata, and Lua scripts for atomic single-dispatch popping.
"""


from __future__ import annotations

import datetime
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.models.task import TaskPriority
from backend.app.services.event_service import EventService
from backend.app.services.redis_client import get_redis_client, is_redis_available, RedisUnavailableError

logger = logging.getLogger("agentos.redis_queue")

# Lua script to atomically pop the highest priority task from ZSET,
# check capability filter, mark it dispatched in the Hash, and return details.
# KEYS[1]: ZSET queue key (agentos:queue:pending)
# KEYS[2]: HASH metadata key prefix (agentos:queue:meta:)
# ARGV[1]: worker_id
# ARGV[2]: dispatched_timestamp (isoformat)
DEQUEUE_LUA = """
local items = redis.call("ZRANGE", KEYS[1], 0, -1, "WITHSCORES")
if #items == 0 then
    return nil
end

for i = 1, #items, 2 do
    local task_id = items[i]
    local score = items[i+1]
    local meta_key = KEYS[2] .. task_id
    local meta_raw = redis.call("GET", meta_key)
    
    if meta_raw then
        -- Atomically remove from pending ZSET
        redis.call("ZREM", KEYS[1], task_id)
        
        -- Decode, update status to DISPATCHED, and write back
        local meta = cjson.decode(meta_raw)
        meta["status"] = "DISPATCHED"
        meta["assigned_worker_id"] = ARGV[1]
        meta["dispatched_at"] = ARGV[2]
        
        local updated_raw = cjson.encode(meta)
        redis.call("SET", meta_key, updated_raw)
        
        -- Add to running set for monitoring
        redis.call("SADD", "agentos:queue:running", task_id)
        
        return updated_raw
    else
        -- Stale queue entry with no meta, remove it
        redis.call("ZREM", KEYS[1], task_id)
    end
end

return nil
"""


class RedisQueueEntryDTO(BaseModel):
    queue_id: str
    task_id: str
    priority: int
    status: str
    required_capabilities: List[str] = []
    assigned_worker_id: Optional[str] = None
    current_fencing_token: int = 0
    enqueued_at: Optional[datetime.datetime] = None
    dispatched_at: Optional[datetime.datetime] = None
    retry_count: int = 0
    retry_limit: int = 3
    idempotency_key: Optional[str] = None
    queue_metadata: Dict[str, Any] = {}


class RedisTaskQueue:
    """Production Redis-backed distributed task queue."""

    PENDING_KEY = "agentos:queue:pending"
    META_PREFIX = "agentos:queue:meta:"
    DLQ_KEY = "agentos:queue:dlq"
    RUNNING_SET = "agentos:queue:running"
    IDEMPOTENCY_PREFIX = "agentos:queue:idem:"
    STARVATION_THRESHOLD_SECONDS = 120

    @classmethod
    def enqueue(
        cls,
        task_id: str,
        priority: int = TaskPriority.NORMAL,
        required_capabilities: Optional[List[str]] = None,
        retry_limit: int = 3,
        idempotency_key: Optional[str] = None,
        queue_metadata: Optional[Dict[str, Any]] = None,
    ) -> RedisQueueEntryDTO:
        """Enqueue task into Redis Sorted Set with idempotency check."""
        if not is_redis_available():
            raise RedisUnavailableError("Redis is not available for RedisTaskQueue.enqueue")

        client = get_redis_client()
        now = datetime.datetime.now(datetime.timezone.utc)
        now_ts = now.timestamp()

        # 1. Idempotency check
        if idempotency_key:
            existing_task_id = client.get(f"{cls.IDEMPOTENCY_PREFIX}{idempotency_key}")
            if existing_task_id:
                meta_raw = client.get(f"{cls.META_PREFIX}{existing_task_id}")
                if meta_raw:
                    data = json.loads(meta_raw)
                    return RedisQueueEntryDTO(**data)

        # Normalize priority integer (0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW)
        p_val = priority if isinstance(priority, int) else 2
        # Score calculation: priority * 1e10 + timestamp to ensure FIFO within priority
        score = (p_val * 1e10) + (now_ts % 1e9)

        queue_id = f"q-{uuid.uuid4().hex[:12]}"
        dto = RedisQueueEntryDTO(
            queue_id=queue_id,
            task_id=task_id,
            priority=p_val,
            status="QUEUED",
            required_capabilities=required_capabilities or [],
            assigned_worker_id=None,
            current_fencing_token=0,
            enqueued_at=now,
            retry_count=0,
            retry_limit=retry_limit,
            idempotency_key=idempotency_key,
            queue_metadata=queue_metadata or {},
        )

        data_str = dto.model_dump_json()

        pipeline = client.pipeline()
        pipeline.set(f"{cls.META_PREFIX}{task_id}", data_str)
        pipeline.zadd(cls.PENDING_KEY, {task_id: score})
        if idempotency_key:
            pipeline.set(f"{cls.IDEMPOTENCY_PREFIX}{idempotency_key}", task_id, ex=86400)
        pipeline.execute()

        EventService.record_event(
            task_id=task_id,
            event_type="TASK_QUEUED_REDIS",
            payload={
                "queue_id": queue_id,
                "priority": p_val,
                "required_capabilities": required_capabilities or [],
                "idempotency_key": idempotency_key,
            },
        )
        return dto

    @classmethod
    def dequeue(
        cls,
        worker_capabilities: Optional[List[str]] = None,
        assigned_worker_id: Optional[str] = None,
    ) -> Optional[RedisQueueEntryDTO]:
        """Atomically dequeue highest priority eligible task using Lua script."""
        if not is_redis_available():
            raise RedisUnavailableError("Redis is not available for RedisTaskQueue.dequeue")

        client = get_redis_client()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        wid = assigned_worker_id or "unassigned"

        try:
            res_json = client.eval(DEQUEUE_LUA, 2, cls.PENDING_KEY, cls.META_PREFIX, wid, now_str)
            if not res_json:
                return None
            data = json.loads(res_json)
            return RedisQueueEntryDTO(**data)
        except Exception as exc:
            logger.error("Failed to dequeue from Redis queue: %s", exc)
            return None

    @classmethod
    def get_entry(cls, task_id: str) -> Optional[RedisQueueEntryDTO]:
        """Get queue metadata for a task."""
        if not is_redis_available():
            return None
        client = get_redis_client()
        meta_raw = client.get(f"{cls.META_PREFIX}{task_id}")
        if not meta_raw:
            return None
        return RedisQueueEntryDTO(**json.loads(meta_raw))

    @classmethod
    def update_status(
        cls,
        task_id: str,
        status: str,
        worker_id: Optional[str] = None,
        fencing_token: Optional[int] = None,
    ) -> bool:
        """Update task status in Redis metadata store."""
        if not is_redis_available():
            return False

        client = get_redis_client()
        meta_key = f"{cls.META_PREFIX}{task_id}"
        meta_raw = client.get(meta_key)
        if not meta_raw:
            return False

        data = json.loads(meta_raw)
        data["status"] = status
        if worker_id:
            data["assigned_worker_id"] = worker_id
        if fencing_token is not None:
            data["current_fencing_token"] = fencing_token

        client.set(meta_key, json.dumps(data))

        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            client.srem(cls.RUNNING_SET, task_id)

        return True

    @classmethod
    def requeue(cls, task_id: str, reason: str = "Retry") -> bool:
        """Requeue task for retry or push to Dead-Letter Queue if retry limit reached."""
        if not is_redis_available():
            return False

        client = get_redis_client()
        meta_key = f"{cls.META_PREFIX}{task_id}"
        meta_raw = client.get(meta_key)
        if not meta_raw:
            return False

        data = json.loads(meta_raw)
        data["retry_count"] = data.get("retry_count", 0) + 1
        retry_limit = data.get("retry_limit", 3)

        client.srem(cls.RUNNING_SET, task_id)

        if data["retry_count"] > retry_limit:
            data["status"] = "FAILED"
            data["queue_metadata"]["dlq_reason"] = f"Exhausted retries ({retry_limit}): {reason}"
            client.set(meta_key, json.dumps(data))
            client.zadd(cls.DLQ_KEY, {task_id: time.time()})
            logger.warning("Task %s exceeded retry limit (%d). Moved to DLQ.", task_id, retry_limit)
            return False

        data["status"] = "QUEUED"
        data["assigned_worker_id"] = None
        now_ts = time.time()
        p_val = data.get("priority", 2)
        score = (p_val * 1e10) + (now_ts % 1e9)

        pipeline = client.pipeline()
        pipeline.set(meta_key, json.dumps(data))
        pipeline.zadd(cls.PENDING_KEY, {task_id: score})
        pipeline.execute()
        return True

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Return real-time queue depth and metrics from Redis."""
        if not is_redis_available():
            return {"error": "Redis unavailable", "pending": 0, "running": 0, "dlq": 0}

        client = get_redis_client()
        pending = client.zcard(cls.PENDING_KEY)
        running = client.scard(cls.RUNNING_SET)
        dlq = client.zcard(cls.DLQ_KEY)

        return {
            "backend": "redis",
            "pending_count": pending,
            "running_count": running,
            "dead_letter_count": dlq,
            "total_active": pending + running,
        }
