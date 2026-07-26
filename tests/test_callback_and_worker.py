from unittest.mock import AsyncMock

from executor.clients.agent import CallbackDeliveryError
from executor.exceptions.execution import InfrastructureError
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.state import CallbackStatus, ExecutionStatus
from executor.services.callback import CallbackService
from executor.workers.execution import ExecutionWorker


class MemoryCallbackRepository:
    def __init__(self, state) -> None:
        self.state = state

    async def mark_callback_pending(self, execution_id: str, *, event_id: str):
        self.state.callback_status = CallbackStatus.PENDING
        self.state.callback_event_id = event_id
        return self.state

    async def record_callback_attempt(
        self,
        execution_id: str,
        *,
        error: str | None,
    ):
        self.state.callback_attempts += 1
        self.state.callback_error = error
        return self.state

    async def mark_callback_delivered(self, execution_id: str):
        self.state.callback_status = CallbackStatus.DELIVERED
        return self.state

    async def mark_callback_failed(self, execution_id: str, *, error: str):
        self.state.callback_status = CallbackStatus.FAILED
        self.state.callback_error = error
        return self.state


async def test_callback_retries_without_changing_execution_status(
    command,
) -> None:
    state = RedisExecutionRepository.build_initial_state(command)
    state.status = ExecutionStatus.SUCCEEDED
    from datetime import UTC, datetime

    state.completed_at = datetime.now(UTC)
    repository = MemoryCallbackRepository(state)
    client = AsyncMock()
    client.send.side_effect = [
        CallbackDeliveryError("temporary"),
        None,
    ]
    service = CallbackService(
        repository=repository,  # type: ignore[arg-type]
        client=client,
        max_attempts=2,
        backoff_seconds=0.001,
    )

    result = await service.deliver(state)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert result.callback_status == CallbackStatus.DELIVERED
    assert result.callback_attempts == 2
    assert client.send.call_count == 2


async def test_worker_does_not_ack_infrastructure_failure(command) -> None:
    redis_client = AsyncMock()
    handler = AsyncMock()
    handler.execute.side_effect = InfrastructureError("offline")
    worker = ExecutionWorker(
        redis_client=redis_client,
        execution_handler=handler,
        consumer_name="worker-1",
        recovery_service=AsyncMock(),
    )

    await worker._process_message("1-0", command)

    redis_client.acknowledge.assert_not_awaited()


async def test_worker_acks_completed_processing(command) -> None:
    redis_client = AsyncMock()
    handler = AsyncMock()
    worker = ExecutionWorker(
        redis_client=redis_client,
        execution_handler=handler,
        consumer_name="worker-1",
        recovery_service=AsyncMock(),
    )

    await worker._process_message("1-0", command)

    redis_client.acknowledge.assert_awaited_once_with("1-0")

