from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from executor.exceptions.execution import (
    CodeExecutionError,
    InfrastructureError,
)


class JupyterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_type: Literal["stream", "execute_result", "display_data"]
    name: str | None = None
    text: str | None = None
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JupyterExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_count: int | None = None
    outputs: list[JupyterOutput] = Field(default_factory=list)
    payload: list[dict[str, Any]] = Field(default_factory=list)


class JupyterMessageCollector:
    def __init__(
        self,
        *,
        request_msg_id: str,
        step_id: str,
    ) -> None:
        self.request_msg_id = request_msg_id
        self.step_id = step_id
        self.outputs: list[JupyterOutput] = []
        self.execution_count: int | None = None
        self.payload: list[dict[str, Any]] = []
        self._reply_received = False
        self._idle_received = False
        self._reply_status: str | None = None
        self._error_type: str | None = None
        self._error_message: str | None = None
        self._traceback: list[str] = []
        self._clear_on_next_output = False

    def collect(self, message: dict[str, Any]) -> bool:
        if not self._is_related_message(message):
            return False
        header = message.get("header", {})
        content = message.get("content", {})
        if not isinstance(header, dict) or not isinstance(content, dict):
            raise InfrastructureError("Invalid Jupyter message")
        msg_type = header.get("msg_type")

        match msg_type:
            case "stream":
                self._collect_stream(content)
            case "execute_result":
                self._collect_result(content)
            case "display_data":
                self._collect_display_data(content)
            case "clear_output":
                self._collect_clear_output(content)
            case "error":
                self._collect_error(content)
            case "execute_reply":
                self._collect_execute_reply(content)
            case "status":
                self._collect_status(content)
        return self.is_complete

    @property
    def is_complete(self) -> bool:
        return self._reply_received and self._idle_received

    def build_result(self) -> JupyterExecutionResult:
        if not self.is_complete:
            raise InfrastructureError("Jupyter execution is not complete")
        if self._reply_status != "ok":
            raise CodeExecutionError(
                step_id=self.step_id,
                error_type=self._error_type or "CodeExecutionError",
                error_message=(
                    self._error_message or "Jupyter code execution failed"
                ),
                traceback=(
                    "\n".join(self._traceback) if self._traceback else None
                ),
            )
        return JupyterExecutionResult(
            execution_count=self.execution_count,
            outputs=self.outputs,
            payload=self.payload,
        )

    def _is_related_message(self, message: dict[str, Any]) -> bool:
        parent_header = message.get("parent_header", {})
        return (
            isinstance(parent_header, dict)
            and parent_header.get("msg_id") == self.request_msg_id
        )

    def _prepare_output(self) -> None:
        if self._clear_on_next_output:
            self.outputs.clear()
            self._clear_on_next_output = False

    def _collect_stream(self, content: dict[str, Any]) -> None:
        self._prepare_output()
        self.outputs.append(
            JupyterOutput(
                output_type="stream",
                name=str(content.get("name", "stdout")),
                text=str(content.get("text", "")),
            )
        )

    def _collect_result(self, content: dict[str, Any]) -> None:
        self._prepare_output()
        count = content.get("execution_count")
        self.execution_count = count if isinstance(count, int) else None
        self.outputs.append(
            JupyterOutput(
                output_type="execute_result",
                data=self._as_dict(content.get("data")),
                metadata=self._as_dict(content.get("metadata")),
            )
        )

    def _collect_display_data(self, content: dict[str, Any]) -> None:
        self._prepare_output()
        self.outputs.append(
            JupyterOutput(
                output_type="display_data",
                data=self._as_dict(content.get("data")),
                metadata=self._as_dict(content.get("metadata")),
            )
        )

    def _collect_clear_output(self, content: dict[str, Any]) -> None:
        if bool(content.get("wait", False)):
            self._clear_on_next_output = True
        else:
            self.outputs.clear()

    def _collect_error(self, content: dict[str, Any]) -> None:
        self._error_type = str(
            content.get("ename", "CodeExecutionError")
        )
        self._error_message = str(content.get("evalue", ""))
        self._traceback = self._as_string_list(content.get("traceback"))

    def _collect_execute_reply(self, content: dict[str, Any]) -> None:
        self._reply_received = True
        self._reply_status = str(content.get("status", "error"))
        count = content.get("execution_count")
        if isinstance(count, int):
            self.execution_count = count
        payload = content.get("payload")
        if isinstance(payload, list):
            self.payload = [
                item for item in payload if isinstance(item, dict)
            ]
        if self._reply_status == "error":
            self._collect_error(content)
        elif self._reply_status == "aborted":
            self._error_type = "ExecutionAborted"
            self._error_message = "Jupyter kernel aborted the execution"

    def _collect_status(self, content: dict[str, Any]) -> None:
        if content.get("execution_state") == "idle":
            self._idle_received = True

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]

