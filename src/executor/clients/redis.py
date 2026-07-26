import asyncio
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from executor.exceptions.execution import (
    DuplicateExecutionError,
    InfrastructureError,
)
from executor.schemas.command import ExecutionCommand
from executor.schemas.state import ExecutionState

_ATOMIC_SUBMIT_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return {0, ''}
end
redis.call('SET', KEYS[1], ARGV[1])
local message_id = redis.call(
    'XADD', KEYS[2], '*', 'payload', ARGV[2]
)
return {1, message_id}
"""


class RedisStreamClient:
    def __init__(
        self,
        redis_url: str,
        stream_name: str = "execution:commands",
        group_name: str = "execution-workers",
        connect_timeout_seconds: float = 5.0,
    ) -> None:
        self.stream_name = stream_name
        self.group_name = group_name
        self.connect_timeout_seconds = connect_timeout_seconds
        self._redis: Redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_timeout_seconds,
            socket_timeout=connect_timeout_seconds,
        )

    async def initialize(self) -> None:
        try:
            async with asyncio.timeout(self.connect_timeout_seconds):
                await self._redis.ping()
                await self._create_consumer_group()
        except TimeoutError as exc:
            raise InfrastructureError("Redis initialization timed out") from exc
        except RedisError as exc:
            raise InfrastructureError(
                f"Redis initialization failed: {exc}"
            ) from exc

    async def _create_consumer_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                name=self.stream_name,
                groupname=self.group_name,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def submit(
        self,
        *,
        state_key: str,
        state: ExecutionState,
        command: ExecutionCommand,
    ) -> str:
        """Atomically create state and enqueue a command."""
        try:
            result = await self._redis.eval(
                _ATOMIC_SUBMIT_SCRIPT,
                2,
                state_key,
                self.stream_name,
                state.model_dump_json(),
                command.model_dump_json(),
            )
        except RedisError as exc:
            raise InfrastructureError(
                f"Atomic execution submission failed: {exc}"
            ) from exc

        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise InfrastructureError("Redis returned an invalid submit result")
        if int(result[0]) != 1:
            raise DuplicateExecutionError(command.execution_id)
        return str(result[1])

    async def publish(self, command: ExecutionCommand) -> str:
        try:
            return str(
                await self._redis.xadd(
                    name=self.stream_name,
                    fields={"payload": command.model_dump_json()},
                )
            )
        except RedisError as exc:
            raise InfrastructureError(
                f"Redis command publish failed: {exc}"
            ) from exc

    async def consume(
        self,
        consumer_name: str,
        count: int = 1,
        block_ms: int = 5_000,
    ) -> list[tuple[str, ExecutionCommand]]:
        try:
            response = await self._redis.xreadgroup(
                groupname=self.group_name,
                consumername=consumer_name,
                streams={self.stream_name: ">"},
                count=count,
                block=block_ms,
            )
        except RedisError as exc:
            raise InfrastructureError(
                f"Redis stream consume failed: {exc}"
            ) from exc
        return self._parse_stream_response(response)

    async def claim_stale(
        self,
        consumer_name: str,
        *,
        min_idle_ms: int,
        count: int = 1,
        start_id: str = "0-0",
    ) -> tuple[str, list[tuple[str, ExecutionCommand]]]:
        try:
            response = await self._redis.xautoclaim(
                name=self.stream_name,
                groupname=self.group_name,
                consumername=consumer_name,
                min_idle_time=min_idle_ms,
                start_id=start_id,
                count=count,
            )
        except RedisError as exc:
            raise InfrastructureError(
                f"Redis pending claim failed: {exc}"
            ) from exc

        if not isinstance(response, (list, tuple)) or len(response) < 2:
            raise InfrastructureError("Redis returned an invalid XAUTOCLAIM result")
        next_id = str(response[0])
        messages = response[1]
        parsed = self._parse_messages(messages)
        return next_id, parsed

    @staticmethod
    def _parse_stream_response(
        response: Any,
    ) -> list[tuple[str, ExecutionCommand]]:
        commands: list[tuple[str, ExecutionCommand]] = []
        for _, messages in response:
            commands.extend(RedisStreamClient._parse_messages(messages))
        return commands

    @staticmethod
    def _parse_messages(
        messages: Any,
    ) -> list[tuple[str, ExecutionCommand]]:
        commands: list[tuple[str, ExecutionCommand]] = []
        for message_id, fields in messages:
            payload = fields.get("payload")
            if not isinstance(payload, str):
                raise InfrastructureError(
                    f"Redis message has no payload: {message_id}"
                )
            commands.append(
                (
                    str(message_id),
                    ExecutionCommand.model_validate_json(payload),
                )
            )
        return commands

    async def acknowledge(self, message_id: str) -> int:
        try:
            return int(
                await self._redis.xack(
                    self.stream_name,
                    self.group_name,
                    message_id,
                )
            )
        except RedisError as exc:
            raise InfrastructureError(
                f"Redis acknowledgement failed: {exc}"
            ) from exc

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
    ) -> bool | None:
        try:
            return await self._redis.set(name=key, value=value, nx=nx)
        except RedisError as exc:
            raise InfrastructureError(f"Redis SET failed: {exc}") from exc

    async def get(self, key: str) -> str | None:
        try:
            value = await self._redis.get(key)
        except RedisError as exc:
            raise InfrastructureError(f"Redis GET failed: {exc}") from exc
        return str(value) if value is not None else None

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except RedisError as exc:
            raise InfrastructureError(f"Redis ping failed: {exc}") from exc

    async def close(self) -> None:
        await self._redis.aclose()

