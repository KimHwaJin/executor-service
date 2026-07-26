from executor.clients.redis import RedisStreamClient
from executor.config.logging import get_logger
from executor.exceptions.execution import (
    DuplicateExecutionError,
    InfrastructureError,
)
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.command import ExecutionCommand
from executor.schemas.state import ExecutionState

logger = get_logger(__name__)


class SubmissionService:
    def __init__(
        self,
        repository: RedisExecutionRepository,
        redis_stream: RedisStreamClient,
    ) -> None:
        self.repository = repository
        self.redis_stream = redis_stream

    async def submit(self, command: ExecutionCommand) -> ExecutionState:
        state = self.repository.build_initial_state(command)
        try:
            message_id = await self.redis_stream.submit(
                state_key=self.repository.key(command.execution_id),
                state=state,
                command=command,
            )
        except DuplicateExecutionError:
            raise
        except InfrastructureError:
            raise
        except Exception as exc:
            logger.exception(
                "Execution submission failed: execution_id=%s",
                command.execution_id,
            )
            raise InfrastructureError(
                f"Execution submission failed: {exc}"
            ) from exc

        logger.info(
            "Execution submitted: execution_id=%s message_id=%s steps=%d",
            command.execution_id,
            message_id,
            len(command.steps),
        )
        return state

