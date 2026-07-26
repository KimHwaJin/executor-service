from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from executor.schemas.state import ExecutionState, ExecutionStatus


class CallbackError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str | None = None
    error_type: str
    message: str


class ExecutionCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: Literal["EXECUTION_SUCCEEDED", "EXECUTION_FAILED"]
    execution_id: str
    thread_id: str
    status: ExecutionStatus
    completed_at: datetime
    result: dict[str, Any] | None = None
    error: CallbackError | None = None

    @classmethod
    def from_state(
        cls,
        state: ExecutionState,
        *,
        event_id: str,
    ) -> "ExecutionCallback":
        if not state.is_terminal or state.completed_at is None:
            raise ValueError("Callback requires a terminal execution state")

        error = None
        if state.status == ExecutionStatus.FAILED:
            error = CallbackError(
                step_id=state.error_step_id,
                error_type=state.error_type or "ExecutionFailed",
                message=state.error_message or "Execution failed",
            )

        return cls(
            event_id=event_id,
            event_type=(
                "EXECUTION_SUCCEEDED"
                if state.status == ExecutionStatus.SUCCEEDED
                else "EXECUTION_FAILED"
            ),
            execution_id=state.execution_id,
            thread_id=state.thread_id,
            status=state.status,
            completed_at=state.completed_at,
            result=state.result,
            error=error,
        )

