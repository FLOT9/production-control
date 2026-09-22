from dataclasses import dataclass
from time import perf_counter

import httpx

from src.integrations.webhooks.exceptions import WebhookHttpError


@dataclass(frozen=True, slots=True)
class WebhookHttpResponse:
    status_code: int
    body: str
    duration_ms: int


MAX_RESPONSE_BODY_LENGTH = 2000


class WebhookHttpClient:
    async def post(
        self,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> WebhookHttpResponse:
        started_at = perf_counter()

        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        **headers,
                    },
                    timeout=timeout_seconds,
                )
        except httpx.RequestError as error:
            duration_ms = round((perf_counter() - started_at) * 1000)
            raise WebhookHttpError(
                message=f"{type(error).__name__}: {error}",
                duration_ms=duration_ms,
            ) from error

        duration_ms = round((perf_counter() - started_at) * 1000)

        return WebhookHttpResponse(
            status_code=response.status_code,
            body=response.text[:MAX_RESPONSE_BODY_LENGTH],
            duration_ms=duration_ms,
        )
