import asyncio
import os
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI

from executor.api.executions import router as executions_router
from executor.api.health import router as health_router
from executor.clients.agent import AgentCallbackClient
from executor.clients.jupyter import JupyterServerClient
from executor.clients.redis import RedisStreamClient
from executor.config.logging import get_logger, setup_logging
from executor.config.settings import get_settings
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.runtime.runner import JupyterExecutionRunner
from executor.services.callback import CallbackService
from executor.services.execution import ExecutionService
from executor.services.processor import ExecutionProcessor
from executor.services.recovery import PendingRecoveryService
from executor.services.submission import SubmissionService
from executor.workers.execution import ExecutionWorker


def _consumer_name(prefix: str) -> str:
    return (
        f"{prefix}-{socket.gethostname()}-{os.getpid()}-"
        f"{uuid4().hex[:8]}"
    )


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        service_name=settings.service_name,
    )
    logger = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        consumer_name = _consumer_name(settings.consumer_name_prefix)
        redis_client = RedisStreamClient(
            redis_url=settings.redis_url,
            stream_name=settings.redis_stream_name,
            group_name=settings.redis_group_name,
            connect_timeout_seconds=(
                settings.redis_connect_timeout_seconds
            ),
        )
        repository = RedisExecutionRepository(
            redis_client=redis_client,
            key_prefix=settings.redis_execution_key_prefix,
        )
        submission_service = SubmissionService(
            repository=repository,
            redis_stream=redis_client,
        )
        jupyter_client = JupyterServerClient(
            base_url=settings.jupyter_base_url,
            token=settings.jupyter_token,
            request_timeout_seconds=(
                settings.jupyter_request_timeout_seconds
            ),
            websocket_open_timeout_seconds=(
                settings.jupyter_websocket_open_timeout_seconds
            ),
            websocket_ping_interval_seconds=(
                settings.jupyter_websocket_ping_interval_seconds
            ),
            websocket_ping_timeout_seconds=(
                settings.jupyter_websocket_ping_timeout_seconds
            ),
            websocket_protocol=settings.jupyter_websocket_protocol,
        )
        callback_client = AgentCallbackClient(
            timeout_seconds=settings.callback_timeout_seconds
        )
        callback_service = CallbackService(
            repository=repository,
            client=callback_client,
            max_attempts=settings.callback_max_attempts,
            backoff_seconds=settings.callback_backoff_seconds,
        )
        execution_service = ExecutionService(
            repository=repository,
            runner=JupyterExecutionRunner(jupyter_client),
            kernel_name_resolver=settings.get_kernel_name,
            executor_id=consumer_name,
        )
        processor = ExecutionProcessor(
            repository=repository,
            execution_service=execution_service,
            callback_service=callback_service,
            jupyter_client=jupyter_client,
        )
        recovery_service = PendingRecoveryService(
            redis_client=redis_client,
            consumer_name=consumer_name,
            min_idle_ms=settings.redis_pending_idle_ms,
            interval_seconds=settings.redis_claim_interval_seconds,
        )
        worker = ExecutionWorker(
            redis_client=redis_client,
            execution_handler=processor,
            consumer_name=consumer_name,
            recovery_service=recovery_service,
            max_concurrency=settings.max_concurrency,
            block_ms=settings.redis_block_ms,
            batch_size=settings.redis_batch_size,
        )

        logger.info("Connecting to Redis")
        try:
            await redis_client.initialize()
        except Exception:
            logger.exception("Redis initialization failed")
            await redis_client.close()
            await jupyter_client.close()
            await callback_client.close()
            raise

        app.state.redis_client = redis_client
        app.state.execution_repository = repository
        app.state.submission_service = submission_service
        app.state.execution_worker = worker
        worker_task = asyncio.create_task(
            worker.run(),
            name="execution-worker",
        )
        logger.info("Executor API and worker started")

        try:
            yield
        finally:
            worker.stop()
            try:
                async with asyncio.timeout(
                    settings.shutdown_timeout_seconds
                ):
                    await worker_task
            except TimeoutError:
                logger.warning(
                    "Worker shutdown timed out; preserving remote Jupyter "
                    "session and cancelling the local monitor"
                )
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
            await callback_client.close()
            await jupyter_client.close()
            await redis_client.close()
            logger.info("Executor API and worker stopped")

    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(executions_router)
    return app


app = create_app()

