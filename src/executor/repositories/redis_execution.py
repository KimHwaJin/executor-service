from datetime import UTC, datetime
from typing import Any

from executor.clients.redis import RedisStreamClient
from executor.exceptions.execution import (
    DuplicateExecutionError,
    ExecutionNotFoundError,
    ExecutionStepNotFoundError,
)
from executor.schemas.command import ExecutionCommand
from executor.schemas.state import (
    CallbackStatus,
    ExecutionState,
    ExecutionStatus,
    StepExecutionState,
    StepStatus,
)


class RedisExecutionRepository:
    def __init__(
        self,
        redis_client: RedisStreamClient,
        key_prefix: str = "execution",
    ) -> None:
        self.redis_client = redis_client
        self.key_prefix = key_prefix

    def key(self, execution_id: str) -> str:
        return f"{self.key_prefix}:{execution_id}"

    @staticmethod
    def build_initial_state(command: ExecutionCommand) -> ExecutionState:
        return ExecutionState(
            execution_id=command.execution_id,
            thread_id=command.thread_id,
            execution_environment=command.execution_environment,
            callback_url=command.callback_url,
            steps=[
                StepExecutionState(
                    step_id=step.step_id,
                    name=step.name,
                    order=index,
                )
                for index, step in enumerate(command.steps, start=1)
            ],
        )

    async def create(self, command: ExecutionCommand) -> ExecutionState:
        state = self.build_initial_state(command)
        created = await self.redis_client.set(
            self.key(command.execution_id),
            state.model_dump_json(),
            nx=True,
        )
        if not created:
            raise DuplicateExecutionError(command.execution_id)
        return state

    async def get(self, execution_id: str) -> ExecutionState | None:
        payload = await self.redis_client.get(self.key(execution_id))
        if payload is None:
            return None
        return ExecutionState.model_validate_json(payload)

    async def get_required(self, execution_id: str) -> ExecutionState:
        state = await self.get(execution_id)
        if state is None:
            raise ExecutionNotFoundError(execution_id)
        return state

    async def save(self, state: ExecutionState) -> None:
        await self.redis_client.set(
            self.key(state.execution_id),
            state.model_dump_json(),
        )

    async def mark_running(
        self,
        execution_id: str,
        *,
        executor_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        now = datetime.now(UTC)
        state.status = ExecutionStatus.RUNNING
        state.started_at = state.started_at or now
        state.executor_id = executor_id
        state.heartbeat_at = now
        await self.save(state)
        return state

    async def bind_jupyter(
        self,
        execution_id: str,
        *,
        target: str,
        session_id: str,
        kernel_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.jupyter_target = target
        state.session_id = session_id
        state.kernel_id = kernel_id
        state.heartbeat_at = datetime.now(UTC)
        await self.save(state)
        return state

    async def set_request_msg_id(
        self,
        execution_id: str,
        request_msg_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.request_msg_id = request_msg_id
        state.heartbeat_at = datetime.now(UTC)
        await self.save(state)
        return state

    async def mark_step_running(
        self,
        execution_id: str,
        step_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        step = self._find_step(state, step_id)
        step.status = StepStatus.RUNNING
        step.started_at = step.started_at or datetime.now(UTC)
        state.current_step_id = step_id
        state.heartbeat_at = datetime.now(UTC)
        await self.save(state)
        return state

    async def mark_step_succeeded(
        self,
        execution_id: str,
        step_id: str,
        result: dict[str, Any] | None = None,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        step = self._find_step(state, step_id)
        step.status = StepStatus.SUCCEEDED
        step.completed_at = datetime.now(UTC)
        step.result = result
        state.heartbeat_at = datetime.now(UTC)
        await self.save(state)
        return state

    async def mark_step_failed(
        self,
        execution_id: str,
        step_id: str,
        *,
        error_type: str,
        error_message: str,
        traceback: str | None = None,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        step = self._find_step(state, step_id)
        now = datetime.now(UTC)
        step.status = StepStatus.FAILED
        step.completed_at = now
        step.error_type = error_type
        step.error_message = error_message
        step.traceback = traceback
        state.status = ExecutionStatus.FAILED
        state.error_step_id = step_id
        state.error_type = error_type
        state.error_message = error_message
        state.completed_at = now
        state.heartbeat_at = now
        await self.save(state)
        return state

    async def mark_infrastructure_failed(
        self,
        execution_id: str,
        *,
        error_type: str,
        error_message: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.status = ExecutionStatus.FAILED
        state.error_type = error_type
        state.error_message = error_message
        state.completed_at = datetime.now(UTC)
        state.heartbeat_at = state.completed_at
        await self.save(state)
        return state

    async def mark_succeeded(
        self,
        execution_id: str,
        result: dict[str, Any] | None = None,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.status = ExecutionStatus.SUCCEEDED
        state.current_step_id = None
        state.result = result
        state.completed_at = datetime.now(UTC)
        state.heartbeat_at = state.completed_at
        await self.save(state)
        return state

    async def mark_callback_pending(
        self,
        execution_id: str,
        *,
        event_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.callback_status = CallbackStatus.PENDING
        state.callback_event_id = event_id
        state.callback_error = None
        await self.save(state)
        return state

    async def record_callback_attempt(
        self,
        execution_id: str,
        *,
        error: str | None,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.callback_attempts += 1
        state.callback_error = error
        await self.save(state)
        return state

    async def mark_callback_delivered(
        self,
        execution_id: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.callback_status = CallbackStatus.DELIVERED
        state.callback_error = None
        state.callback_delivered_at = datetime.now(UTC)
        await self.save(state)
        return state

    async def mark_callback_failed(
        self,
        execution_id: str,
        *,
        error: str,
    ) -> ExecutionState:
        state = await self.get_required(execution_id)
        state.callback_status = CallbackStatus.FAILED
        state.callback_error = error
        await self.save(state)
        return state

    @staticmethod
    def _find_step(
        state: ExecutionState,
        step_id: str,
    ) -> StepExecutionState:
        for step in state.steps:
            if step.step_id == step_id:
                return step
        raise ExecutionStepNotFoundError(state.execution_id, step_id)

