import asyncio
from uuid import NAMESPACE_URL, uuid5

from executor.clients.agent import (
    AgentCallbackClient,
    CallbackDeliveryError,
)
from executor.config.logging import get_logger
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.callback import ExecutionCallback
from executor.schemas.state import (
    CallbackStatus,
    ExecutionState,
)

logger = get_logger(__name__)


class CallbackService:
    def __init__(
        self,
        *,
        repository: RedisExecutionRepository,
        client: AgentCallbackClient,
        max_attempts: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.repository = repository
        self.client = client
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    async def deliver(self, state: ExecutionState) -> ExecutionState:
        if state.callback_status == CallbackStatus.DELIVERED:
            return state
        if not state.is_terminal:
            raise ValueError("Cannot deliver callback for non-terminal state")

        event_id = state.callback_event_id or str(
            uuid5(
                NAMESPACE_URL,
                f"executor:{state.execution_id}:{state.status}",
            )
        )
        state = await self.repository.mark_callback_pending(
            state.execution_id,
            event_id=event_id,
        )
        callback = ExecutionCallback.from_state(
            state,
            event_id=event_id,
        )
        last_error = "Callback delivery failed"

        for attempt in range(1, self.max_attempts + 1):
            try:
                await self.client.send(state.callback_url, callback)
            except CallbackDeliveryError as exc:
                last_error = str(exc)
                await self.repository.record_callback_attempt(
                    state.execution_id,
                    error=last_error,
                )
                logger.warning(
                    "Callback attempt failed: execution_id=%s attempt=%d/%d",
                    state.execution_id,
                    attempt,
                    self.max_attempts,
                )
                if attempt < self.max_attempts:
                    await asyncio.sleep(
                        self.backoff_seconds * (2 ** (attempt - 1))
                    )
            else:
                await self.repository.record_callback_attempt(
                    state.execution_id,
                    error=None,
                )
                logger.info(
                    "Callback delivered: execution_id=%s event_id=%s",
                    state.execution_id,
                    event_id,
                )
                return await self.repository.mark_callback_delivered(
                    state.execution_id
                )

        logger.error(
            "Callback exhausted retries: execution_id=%s",
            state.execution_id,
        )
        return await self.repository.mark_callback_failed(
            state.execution_id,
            error=last_error,
        )

