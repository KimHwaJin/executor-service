from pydantic import BaseModel, ConfigDict

from executor.schemas.state import ExecutionState, ExecutionStatus


class ExecutionAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    status: ExecutionStatus


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution: ExecutionState

