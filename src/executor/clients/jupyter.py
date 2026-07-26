from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import uuid4

import httpx
from websockets.asyncio.client import ClientConnection, connect

from executor.exceptions.execution import (
    InfrastructureError,
    KernelNotFoundError,
)


@dataclass(frozen=True)
class JupyterSessionInfo:
    session_id: str
    kernel_id: str
    target: str


class JupyterServerClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        request_timeout_seconds: float = 30.0,
        websocket_open_timeout_seconds: float = 30.0,
        websocket_ping_interval_seconds: float = 20.0,
        websocket_ping_timeout_seconds: float = 20.0,
        websocket_protocol: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.websocket_open_timeout_seconds = websocket_open_timeout_seconds
        self.websocket_ping_interval_seconds = (
            websocket_ping_interval_seconds
        )
        self.websocket_ping_timeout_seconds = websocket_ping_timeout_seconds
        self.websocket_protocol = websocket_protocol

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"token {token}"
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=request_timeout_seconds,
        )

    async def create_session(
        self,
        *,
        execution_id: str,
        kernel_name: str,
    ) -> JupyterSessionInfo:
        try:
            response = await self._http.post(
                "/api/sessions",
                json={
                    "name": execution_id,
                    "path": f"executor/{execution_id}.ipynb",
                    "type": "notebook",
                    "kernel": {"name": kernel_name},
                },
            )
            response.raise_for_status()
            payload = response.json()
            return JupyterSessionInfo(
                session_id=str(payload["id"]),
                kernel_id=str(payload["kernel"]["id"]),
                target=self.base_url,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise InfrastructureError(
                f"Jupyter session creation failed: {exc}"
            ) from exc

    @asynccontextmanager
    async def connect_channels(
        self,
        kernel_id: str,
    ) -> AsyncIterator[ClientConnection]:
        websocket_url = self._build_websocket_url(kernel_id)
        try:
            websocket = await connect(
                websocket_url,
                open_timeout=self.websocket_open_timeout_seconds,
                ping_interval=self.websocket_ping_interval_seconds,
                ping_timeout=self.websocket_ping_timeout_seconds,
                max_size=None,
                subprotocols=(
                    [self.websocket_protocol]
                    if self.websocket_protocol
                    else None
                ),
            )
        except Exception as exc:
            raise InfrastructureError(
                "Jupyter WebSocket connection failed: "
                f"kernel_id={kernel_id}"
            ) from exc

        try:
            yield websocket
        finally:
            await websocket.close()

    async def get_kernel(self, kernel_id: str) -> dict[str, Any]:
        try:
            response = await self._http.get(f"/api/kernels/{kernel_id}")
            if response.status_code == 404:
                raise KernelNotFoundError(kernel_id)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("Kernel response is not an object")
            return payload
        except KernelNotFoundError:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise InfrastructureError(
                f"Failed to get kernel: {kernel_id}"
            ) from exc

    async def interrupt_kernel(self, kernel_id: str) -> None:
        try:
            response = await self._http.post(
                f"/api/kernels/{kernel_id}/interrupt"
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise InfrastructureError(
                f"Kernel interrupt failed: {kernel_id}"
            ) from exc

    async def delete_session(self, session_id: str) -> None:
        try:
            response = await self._http.delete(f"/api/sessions/{session_id}")
            if response.status_code not in {204, 404, 410}:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise InfrastructureError(
                f"Jupyter session deletion failed: {session_id}"
            ) from exc

    async def close(self) -> None:
        await self._http.aclose()

    def _build_websocket_url(self, kernel_id: str) -> str:
        parsed = urlparse(self.base_url)
        query = {"session_id": uuid4().hex}
        if self.token:
            query["token"] = self.token
        return urlunparse(
            (
                "wss" if parsed.scheme == "https" else "ws",
                parsed.netloc,
                (
                    f"{parsed.path.rstrip('/')}"
                    f"/api/kernels/{kernel_id}/channels"
                ),
                "",
                urlencode(query),
                "",
            )
        )

