import time

from executor.clients.redis import RedisStreamClient
from executor.schemas.command import ExecutionCommand


class PendingRecoveryService:
    def __init__(
        self,
        *,
        redis_client: RedisStreamClient,
        consumer_name: str,
        min_idle_ms: int,
        interval_seconds: float,
    ) -> None:
        self.redis_client = redis_client
        self.consumer_name = consumer_name
        self.min_idle_ms = min_idle_ms
        self.interval_seconds = interval_seconds
        self._cursor = "0-0"
        self._next_claim_at = 0.0

    async def claim(
        self,
        *,
        count: int,
    ) -> list[tuple[str, ExecutionCommand]]:
        now = time.monotonic()
        if now < self._next_claim_at:
            return []
        self._next_claim_at = now + self.interval_seconds
        self._cursor, messages = await self.redis_client.claim_stale(
            self.consumer_name,
            min_idle_ms=self.min_idle_ms,
            count=count,
            start_id=self._cursor,
        )
        if self._cursor == "0-0":
            self._cursor = "0-0"
        return messages

