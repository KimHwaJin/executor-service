from fastapi import APIRouter, HTTPException, Request, status

from executor.exceptions.execution import (
    DuplicateExecutionError,
    InfrastructureError,
)
from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.api import (
    ExecutionAcceptedResponse,
    ExecutionResponse,
)
from executor.schemas.command import ExecutionCommand
from executor.services.submission import SubmissionService

router = APIRouter(prefix="/executions", tags=["executions"])


@router.post(
    "",
    response_model=ExecutionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_execution(
    command: ExecutionCommand,
    request: Request,
) -> ExecutionAcceptedResponse:
    service: SubmissionService = request.app.state.submission_service
    try:
        execution = await service.submit(command)
    except DuplicateExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution submission failed",
        ) from exc
    return ExecutionAcceptedResponse(
        execution_id=execution.execution_id,
        status=execution.status,
    )


@router.get(
    "/{execution_id}",
    response_model=ExecutionResponse,
)
async def get_execution(
    execution_id: str,
    request: Request,
) -> ExecutionResponse:
    repository: RedisExecutionRepository = (
        request.app.state.execution_repository
    )
    try:
        execution = await repository.get(execution_id)
    except InfrastructureError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution state is unavailable",
        ) from exc
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution not found",
        )
    return ExecutionResponse(execution=execution)

