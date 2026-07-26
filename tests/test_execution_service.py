from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from executor.repositories.redis_execution import RedisExecutionRepository
from executor.schemas.command import ExecutionCommand, ExecutionStep
from executor.schemas.state import (
    ExecutionState,
    ExecutionStatus,
    StepStatus,
)
from executor.services.execution import ExecutionService


class MemoryRepository:
    def __init__(self, command: ExecutionCommand) -> None:
        self.state = RedisExecutionRepository.build_initial_state(command)

    async def get_required(self, execution_id: str) -> ExecutionState:
        assert execution_id == self.state.execution_id
        return self.state

    async def mark_running(
        self,
        execution_id: str,
        *,
        executor_id: str,
    ) -> ExecutionState:
        self.state.status = ExecutionStatus.RUNNING
        self.state.executor_id = executor_id
        return self.state

    async def bind_jupyter(self, execution_id: str, **values: str):
        self.state.jupyter_target = values["target"]
        self.state.session_id = values["session_id"]
        self.state.kernel_id = values["kernel_id"]
        return self.state

    async def set_request_msg_id(
        self,
        execution_id: str,
        request_msg_id: str,
    ):
        self.state.request_msg_id = request_msg_id
        return self.state

    async def mark_step_running(
        self,
        execution_id: str,
        step_id: str,
    ):
        step = next(item for item in self.state.steps if item.step_id == step_id)
        step.status = StepStatus.RUNNING
        return self.state

    async def mark_step_succeeded(
        self,
        execution_id: str,
        step_id: str,
        result: dict[str, Any] | None = None,
    ):
        step = next(item for item in self.state.steps if item.step_id == step_id)
        step.status = StepStatus.SUCCEEDED
        step.result = result
        return self.state

    async def mark_succeeded(
        self,
        execution_id: str,
        result: dict[str, Any] | None = None,
    ):
        self.state.status = ExecutionStatus.SUCCEEDED
        return self.state


@dataclass
class Info:
    target: str = "http://jupyter"
    session_id: str = "session-1"
    kernel_id: str = "kernel-1"


class FakeSession:
    session_info = Info()

    def __init__(self) -> None:
        self.steps: list[str] = []
        self.value_exists = False

    async def run(self, step: ExecutionStep) -> dict[str, Any]:
        self.steps.append(step.step_id)
        if step.step_id == "step-1":
            self.value_exists = True
        if step.step_id == "step-2":
            assert self.value_exists
        return {"step_id": step.step_id}


class FakeRunner:
    def __init__(self) -> None:
        self.open_count = 0
        self.session = FakeSession()

    @asynccontextmanager
    async def open(self, **kwargs):
        self.open_count += 1
        await kwargs["on_request_started"]("request-1")
        yield self.session


async def test_steps_share_one_session(command: ExecutionCommand) -> None:
    repository = MemoryRepository(command)
    runner = FakeRunner()
    service = ExecutionService(
        repository=repository,  # type: ignore[arg-type]
        runner=runner,
        kernel_name_resolver=lambda _: "analysis-env",
        executor_id="worker-1",
    )

    result = await service.execute(command)

    assert result.status == ExecutionStatus.SUCCEEDED
    assert runner.open_count == 1
    assert runner.session.steps == ["step-1", "step-2"]
    assert all(step.status == StepStatus.SUCCEEDED for step in result.steps)

