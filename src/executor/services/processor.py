from executor.clients.jupyter import JupyterServerClient
from executor.config.logging import get_logger
from executor.exceptions.execution import (
    InfrastructureError,
    KernelNotFoundError,
)
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.command import ExecutionCommand
from executor.schemas.state import ExecutionStatus
from executor.services.callback import CallbackService
from executor.services.execution import ExecutionService

logger = get_logger(__name__)


class ExecutionProcessor:
    """Combine execution and callback without coupling their retry domains."""

    def __init__(
        self,
        *,
        repository: RedisExecutionRepository,
        execution_service: ExecutionService,
        callback_service: CallbackService,
        jupyter_client: JupyterServerClient,
    ) -> None:
        self.repository = repository
        self.execution_service = execution_service
        self.callback_service = callback_service
        self.jupyter_client = jupyter_client

    async def execute(self, command: ExecutionCommand) -> object:
        state = await self.repository.get_required(command.execution_id)

        if not state.is_terminal and state.status == ExecutionStatus.RUNNING:
            state = await self._recover_running(state.execution_id)
        elif not state.is_terminal:
            state = await self.execution_service.execute(command)

        # Callback failure is persisted and deliberately does not raise. The
        # execution Stream can be ACKed without re-running user code.
        return await self.callback_service.deliver(state)

    async def _recover_running(self, execution_id: str):
        state = await self.repository.get_required(execution_id)
        if not state.kernel_id:
            raise InfrastructureError(
                "RUNNING execution has no kernel binding; "
                "manual reconciliation is required"
            )
        try:
            await self.jupyter_client.get_kernel(state.kernel_id)
        except KernelNotFoundError:
            logger.error(
                "Previously running kernel disappeared: execution_id=%s",
                execution_id,
            )
            return await self.repository.mark_infrastructure_failed(
                execution_id,
                error_type="KernelLost",
                error_message=(
                    "The Jupyter kernel disappeared before its result "
                    "could be recovered"
                ),
            )

        raise InfrastructureError(
            "The previous Jupyter kernel is still alive. The command remains "
            "Pending because WebSocket messages cannot be replayed safely; "
            "user code was not re-executed."
        )

