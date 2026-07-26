import httpx
from pydantic import AnyHttpUrl

from executor.schemas.callback import ExecutionCallback


class CallbackDeliveryError(Exception):
    """A callback attempt failed without changing execution status."""


class AgentCallbackClient:
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._http = httpx.AsyncClient(timeout=timeout_seconds)

    async def send(
        self,
        callback_url: AnyHttpUrl,
        callback: ExecutionCallback,
    ) -> None:
        try:
            response = await self._http.post(
                str(callback_url),
                json=callback.model_dump(mode="json"),
                headers={"Idempotency-Key": callback.event_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CallbackDeliveryError(str(exc)) from exc

    async def close(self) -> None:
        await self._http.aclose()

