import pytest

from executor.schemas.command import ExecutionCommand


@pytest.fixture
def command_payload() -> dict:
    return {
        "execution_id": "exec-001",
        "thread_id": "thread-001",
        "execution_environment": "ANALYSIS",
        "steps": [
            {
                "step_id": "step-1",
                "name": "first",
                "code": "value = 1",
                "timeout_seconds": 30,
            },
            {
                "step_id": "step-2",
                "name": "second",
                "code": "print(value)",
                "timeout_seconds": 30,
            },
        ],
        "callback_url": "http://agent.test/callback",
    }


@pytest.fixture
def command(command_payload: dict) -> ExecutionCommand:
    return ExecutionCommand.model_validate(command_payload)
