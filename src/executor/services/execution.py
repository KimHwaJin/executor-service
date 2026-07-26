from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from executor.config.logging import get_logger
from executor.exceptions.execution import (
    CodeExecutionError,
    InfrastructureError,
)
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.command import ExecutionCommand, ExecutionStep
from executor.schemas.state import ExecutionState, ExecutionStatus

logger = get_logger(__name__)


class SessionStepRunner(Protocol):
    session_info: Any

    async def run(self, step: ExecutionStep) -> dict[str, Any]:
        ...


class ExecutionRunner(Protocol):
    def open(
        self,
        *,
        execution_id: str,
        kernel_name: str,
        on_request_started: Callable[[str], Awaitable[None]],
    ) -> AbstractAsyncContextManager[SessionStepRunner]:
        ...


KernelNameResolver = Callable[[Any], str]


class ExecutionService:
    def __init__(
        self,
        *,
        repository: RedisExecutionRepository,
        runner: ExecutionRunner,
        kernel_name_resolver: KernelNameResolver,
        executor_id: str,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.kernel_name_resolver = kernel_name_resolver
        self.executor_id = executor_id

    async def execute(self, command: ExecutionCommand) -> ExecutionState:
        existing = await self.repository.get_required(command.execution_id)
        if existing.is_terminal:
            return existing
        if existing.status == ExecutionStatus.RUNNING:
            raise InfrastructureError(
                "Execution is already RUNNING; automatic re-execution is "
                f"disabled: {command.execution_id}"
            )

        await self.repository.mark_running(
            command.execution_id,
            executor_id=self.executor_id,
        )
        kernel_name = self.kernel_name_resolver(
            command.execution_environment
        )

        async def request_started(message_id: str) -> None:
            await self.repository.set_request_msg_id(
                command.execution_id,
                message_id,
            )

        async with self.runner.open(
            execution_id=command.execution_id,
            kernel_name=kernel_name,
            on_request_started=request_started,
        ) as session:
            info = session.session_info
            await self.repository.bind_jupyter(
                command.execution_id,
                target=str(info.target),
                session_id=str(info.session_id),
                kernel_id=str(info.kernel_id),
            )
            has_failed_step = False

            for step in command.steps:
                await self.repository.mark_step_running(
                    command.execution_id,
                    step.step_id,
                )
                logger.info(
                    "Step started: execution_id=%s step_id=%s",
                    command.execution_id,
                    step.step_id,
                )
                try:
                    result = await session.run(step)
                except CodeExecutionError as exc:
                    has_failed_step = True
                    state = await self.repository.mark_step_failed(
                        execution_id=command.execution_id,
                        step_id=step.step_id,
                        error_type=exc.error_type,
                        error_message=exc.error_message,
                        traceback=exc.traceback,
                    )
                    logger.warning(
                        "Step failed: execution_id=%s step_id=%s error=%s",
                        command.execution_id,
                        step.step_id,
                        exc.error_message,
                    )
                    if command.stop_on_error:
                        return state
                except InfrastructureError:
                    logger.exception(
                        "Infrastructure failure: execution_id=%s step_id=%s",
                        command.execution_id,
                        step.step_id,
                    )
                    raise
                except Exception as exc:
                    logger.exception(
                        "Unexpected executor failure: "
                        "execution_id=%s step_id=%s",
                        command.execution_id,
                        step.step_id,
                    )
                    raise InfrastructureError(
                        f"Unexpected execution failure: {exc}"
                    ) from exc
                else:
                    await self.repository.mark_step_succeeded(
                        execution_id=command.execution_id,
                        step_id=step.step_id,
                        result=result,
                    )

            if has_failed_step:
                return await self.repository.get_required(
                    command.execution_id
                )
            return await self.repository.mark_succeeded(
                command.execution_id
            )
