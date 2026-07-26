class ExecutionError(Exception):
    """Base exception raised while processing an execution."""


class CodeExecutionError(ExecutionError):
    """User code failure. Persist as FAILED and ACK the command."""

    def __init__(
        self,
        *,
        step_id: str,
        error_type: str,
        error_message: str,
        traceback: str | None = None,
    ) -> None:
        super().__init__(error_message)
        self.step_id = step_id
        self.error_type = error_type
        self.error_message = error_message
        self.traceback = traceback


class InfrastructureError(ExecutionError):
    """Incomplete infrastructure processing. Do not ACK the command."""


class DuplicateExecutionError(ExecutionError):
    def __init__(self, execution_id: str) -> None:
        super().__init__(f"Execution already exists: {execution_id}")
        self.execution_id = execution_id


class ExecutionNotFoundError(ExecutionError):
    def __init__(self, execution_id: str) -> None:
        super().__init__(f"Execution state not found: {execution_id}")
        self.execution_id = execution_id


class ExecutionStepNotFoundError(ExecutionError):
    def __init__(self, execution_id: str, step_id: str) -> None:
        super().__init__(
            "Execution step not found: "
            f"execution_id={execution_id}, step_id={step_id}"
        )
        self.execution_id = execution_id
        self.step_id = step_id


class KernelNotFoundError(InfrastructureError):
    def __init__(self, kernel_id: str) -> None:
        super().__init__(f"Jupyter kernel not found: {kernel_id}")
        self.kernel_id = kernel_id

