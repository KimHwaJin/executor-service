from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from executor.schemas.command import ExecutionEnvironment


class ExecutionStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class CallbackStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class StepExecutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    name: str
    order: int
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None


class ExecutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    thread_id: str
    execution_environment: ExecutionEnvironment
    callback_url: AnyHttpUrl
    status: ExecutionStatus = ExecutionStatus.QUEUED
    current_step_id: str | None = None
    steps: list[StepExecutionState] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_step_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    jupyter_target: str | None = None
    session_id: str | None = None
    kernel_id: str | None = None
    request_msg_id: str | None = None
    executor_id: str | None = None
    heartbeat_at: datetime | None = None

    callback_status: CallbackStatus = CallbackStatus.NOT_REQUESTED
    callback_event_id: str | None = None
    callback_attempts: int = 0
    callback_error: str | None = None
    callback_delivered_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
        }

