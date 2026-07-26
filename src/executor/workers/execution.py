import asyncio
from typing import Protocol

from executor.clients.redis import RedisStreamClient
from executor.config.logging import get_logger
from executor.exceptions.execution import InfrastructureError
from executor.schemas.command import ExecutionCommand
from executor.services.recovery import PendingRecoveryService

logger = get_logger(__name__)


class ExecutionHandler(Protocol):
    async def execute(self, command: ExecutionCommand) -> object:
        ...


class ExecutionWorker:
    def __init__(
        self,
        *,
        redis_client: RedisStreamClient,
        execution_handler: ExecutionHandler,
        consumer_name: str,
        recovery_service: PendingRecoveryService,
        max_concurrency: int = 1,
        block_ms: int = 5_000,
        batch_size: int = 1,
    ) -> None:
        self.redis_client = redis_client
        self.execution_handler = execution_handler
        self.consumer_name = consumer_name
        self.recovery_service = recovery_service
        self.max_concurrency = max_concurrency
        self.block_ms = block_ms
        self.batch_size = batch_size
        self._stop_event = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        logger.info(
            "Execution worker started: consumer=%s",
            self.consumer_name,
        )
        try:
            while not self._stop_event.is_set():
                await self._wait_for_available_slot()
                available = min(
                    self.batch_size,
                    self.max_concurrency - len(self._tasks),
                )
                try:
                    messages = await self.recovery_service.claim(
                        count=available
                    )
                    if not messages:
                        messages = await self.redis_client.consume(
                            consumer_name=self.consumer_name,
                            count=available,
                            block_ms=self.block_ms,
                        )
                except InfrastructureError:
                    logger.exception("Redis worker loop failed")
                    await asyncio.sleep(1)
                    continue

                for message_id, command in messages:
                    task = asyncio.create_task(
                        self._process_message(message_id, command)
                    )
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
        except asyncio.CancelledError:
            logger.info("Execution worker cancellation requested")
            raise
        finally:
            await self._wait_for_running_tasks()
            logger.info(
                "Execution worker stopped: consumer=%s",
                self.consumer_name,
            )

    async def _process_message(
        self,
        message_id: str,
        command: ExecutionCommand,
    ) -> None:
        logger.info(
            "Execution processing started: execution_id=%s message_id=%s",
            command.execution_id,
            message_id,
        )
        try:
            await self.execution_handler.execute(command)
            await self.redis_client.acknowledge(message_id)
        except InfrastructureError:
            logger.exception(
                "Execution remains Pending after infrastructure failure: "
                "execution_id=%s",
                command.execution_id,
            )
        except Exception:
            logger.exception(
                "Unexpected execution processing failure; message is not ACKed: "
                "execution_id=%s",
                command.execution_id,
            )
        else:
            logger.info(
                "Execution message ACKed: execution_id=%s",
                command.execution_id,
            )

    async def _wait_for_available_slot(self) -> None:
        if len(self._tasks) < self.max_concurrency:
            return
        await asyncio.wait(
            self._tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

    async def _wait_for_running_tasks(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def stop(self) -> None:
        self._stop_event.set()

