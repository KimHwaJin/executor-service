from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class ExecutionEnvironment(StrEnum):
    ANALYSIS = "ANALYSIS"
    MODELING = "MODELING"


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    code: str = Field(min_length=1)
    timeout_seconds: int = Field(default=172_800, gt=0)


class ExecutionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_type: Literal["EXECUTE_CODE"] = "EXECUTE_CODE"
    execution_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    execution_environment: ExecutionEnvironment
    steps: list[ExecutionStep] = Field(min_length=1)
    callback_url: AnyHttpUrl
    stop_on_error: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> "ExecutionCommand":
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step_id values must be unique")
        return self

