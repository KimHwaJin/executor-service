import pytest
from pydantic import ValidationError

from executor.schemas.command import ExecutionCommand
from executor.schemas.state import ExecutionStatus


def test_duplicate_step_ids_are_rejected(command_payload: dict) -> None:
    command_payload["steps"][1]["step_id"] = "step-1"
    with pytest.raises(ValidationError, match="step_id values must be unique"):
        ExecutionCommand.model_validate(command_payload)


def test_command_defaults_to_queued_state(command: ExecutionCommand) -> None:
    from executor.repositories.redis_execution import (
        RedisExecutionRepository,
    )

    state = RedisExecutionRepository.build_initial_state(command)
    assert state.status == ExecutionStatus.QUEUED
    assert [step.order for step in state.steps] == [1, 2]
    assert str(state.callback_url) == "http://agent.test/callback"

