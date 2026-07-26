import asyncio
import json
import struct
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from jupyter_client.session import Session
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from executor.clients.jupyter import (
    JupyterServerClient,
    JupyterSessionInfo,
)
from executor.config.logging import get_logger
from executor.exceptions.execution import (
    CodeExecutionError,
    InfrastructureError,
)
from executor.runtime.collector import JupyterMessageCollector
from executor.schemas.command import ExecutionStep

logger = get_logger(__name__)

JUPYTER_V1_PROTOCOL = "v1.kernel.websocket.jupyter.org"
RequestStarted = Callable[[str], Awaitable[None]]


def encode_v1_message(message: dict[str, Any]) -> bytes:
    """Encode the official Jupyter v1 WebSocket binary wire format."""
    buffers = message.get("buffers", [])
    if not isinstance(buffers, list):
        raise InfrastructureError("Jupyter buffers must be a list")
    parts = [
        str(message.get("channel", "shell")).encode(),
        _json_bytes(message.get("header", {})),
        _json_bytes(message.get("parent_header", {})),
        _json_bytes(message.get("metadata", {})),
        _json_bytes(message.get("content", {})),
        *[bytes(buffer) for buffer in buffers],
    ]
    offset_count = len(parts) + 1
    header_size = 8 * (offset_count + 1)
    offsets = [header_size]
    for part in parts:
        offsets.append(offsets[-1] + len(part))
    return (
        struct.pack("<Q", offset_count)
        + struct.pack(f"<{offset_count}Q", *offsets)
        + b"".join(parts)
    )


def decode_message_frame(frame: str | bytes) -> dict[str, Any]:
    if isinstance(frame, str):
        return _json_object(frame.encode())
    try:
        return _decode_v1_message(frame)
    except (InfrastructureError, ValueError, struct.error):
        return _decode_legacy_binary_message(frame)


def _decode_v1_message(frame: bytes) -> dict[str, Any]:
    if len(frame) < 56:
        raise InfrastructureError("Jupyter v1 frame is too short")
    offset_count = struct.unpack_from("<Q", frame, 0)[0]
    if offset_count < 6 or offset_count > 1_000:
        raise InfrastructureError("Invalid Jupyter v1 offset count")
    table_end = 8 * (offset_count + 1)
    if table_end > len(frame):
        raise InfrastructureError("Truncated Jupyter v1 offset table")
    offsets = struct.unpack_from(f"<{offset_count}Q", frame, 8)
    if offsets[0] != table_end or offsets[-1] != len(frame):
        raise InfrastructureError("Invalid Jupyter v1 offsets")
    if any(left > right for left, right in zip(offsets, offsets[1:])):
        raise InfrastructureError("Unordered Jupyter v1 offsets")
    parts = [
        frame[offsets[index] : offsets[index + 1]]
        for index in range(offset_count - 1)
    ]
    message = {
        "channel": parts[0].decode(),
        "header": _json_object(parts[1]),
        "parent_header": _json_object(parts[2]),
        "metadata": _json_object(parts[3]),
        "content": _json_object(parts[4]),
        "buffers": parts[5:],
    }
    return message


def _decode_legacy_binary_message(frame: bytes) -> dict[str, Any]:
    if len(frame) < 8:
        raise InfrastructureError("Jupyter binary frame is too short")
    part_count = struct.unpack_from("!I", frame, 0)[0]
    if part_count < 1 or part_count > 1_000:
        raise InfrastructureError("Invalid Jupyter binary part count")
    table_end = 4 * (part_count + 1)
    if table_end > len(frame):
        raise InfrastructureError("Truncated Jupyter binary offset table")
    offsets = struct.unpack_from(f"!{part_count}I", frame, 4)
    boundaries = [*offsets, len(frame)]
    if offsets[0] != table_end:
        raise InfrastructureError("Invalid Jupyter binary offsets")
    parts = [
        frame[boundaries[index] : boundaries[index + 1]]
        for index in range(part_count)
    ]
    message = _json_object(parts[0])
    message["buffers"] = parts[1:]
    return message


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def _json_object(value: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(value.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InfrastructureError("Invalid Jupyter JSON message") from exc
    if not isinstance(decoded, dict):
        raise InfrastructureError("Jupyter message is not an object")
    return decoded


class JupyterSessionRunner:
    def __init__(
        self,
        *,
        client: JupyterServerClient,
        session_info: JupyterSessionInfo,
        websocket: ClientConnection,
        on_request_started: RequestStarted,
    ) -> None:
        self.client = client
        self.session_info = session_info
        self.websocket = websocket
        self.on_request_started = on_request_started
        self._session = Session()

    async def run(self, step: ExecutionStep) -> dict[str, Any]:
        content = {
            "code": step.code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False,
            "stop_on_error": True,
        }
        message = self._session.msg("execute_request", content=content)
        message["channel"] = "shell"
        request_msg_id = str(message["header"]["msg_id"])
        await self.on_request_started(request_msg_id)
        collector = JupyterMessageCollector(
            request_msg_id=request_msg_id,
            step_id=step.step_id,
        )

        try:
            await self._send(message)
            async with asyncio.timeout(step.timeout_seconds):
                while not collector.is_complete:
                    frame = await self.websocket.recv()
                    collector.collect(decode_message_frame(frame))
        except TimeoutError as exc:
            await self._interrupt_best_effort()
            raise CodeExecutionError(
                step_id=step.step_id,
                error_type="ExecutionTimeout",
                error_message=(
                    f"Step exceeded {step.timeout_seconds} seconds"
                ),
            ) from exc
        except ConnectionClosed as exc:
            raise InfrastructureError(
                "Jupyter WebSocket disconnected while code may still be running; "
                "automatic re-execution is disabled"
            ) from exc
        except CodeExecutionError:
            raise
        except InfrastructureError:
            raise
        except Exception as exc:
            raise InfrastructureError(
                f"Jupyter protocol failure: {exc}"
            ) from exc

        return collector.build_result().model_dump(mode="json")

    async def _send(self, message: dict[str, Any]) -> None:
        if self.websocket.subprotocol == JUPYTER_V1_PROTOCOL:
            await self.websocket.send(encode_v1_message(message))
            return
        await self.websocket.send(
            json.dumps(message, separators=(",", ":"), default=str)
        )

    async def _interrupt_best_effort(self) -> None:
        try:
            await self.client.interrupt_kernel(
                self.session_info.kernel_id
            )
        except InfrastructureError:
            logger.exception(
                "Kernel interrupt failed after timeout: kernel_id=%s",
                self.session_info.kernel_id,
            )


class JupyterExecutionRunner:
    def __init__(self, client: JupyterServerClient) -> None:
        self.client = client

    @asynccontextmanager
    async def open(
        self,
        *,
        execution_id: str,
        kernel_name: str,
        on_request_started: RequestStarted,
    ) -> AsyncIterator[JupyterSessionRunner]:
        info = await self.client.create_session(
            execution_id=execution_id,
            kernel_name=kernel_name,
        )
        preserve_session = False
        try:
            async with self.client.connect_channels(
                info.kernel_id
            ) as websocket:
                yield JupyterSessionRunner(
                    client=self.client,
                    session_info=info,
                    websocket=websocket,
                    on_request_started=on_request_started,
                )
        except (InfrastructureError, asyncio.CancelledError):
            preserve_session = True
            raise
        finally:
            if not preserve_session:
                try:
                    await self.client.delete_session(info.session_id)
                except InfrastructureError:
                    logger.exception(
                        "Jupyter session cleanup failed: session_id=%s",
                        info.session_id,
                    )

