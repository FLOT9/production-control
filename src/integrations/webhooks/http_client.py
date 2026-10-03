import asyncio
from dataclasses import dataclass
from time import perf_counter

import httpx

from src.integrations.webhooks.exceptions import WebhookHttpError
from src.integrations.webhooks.url_policy import UnsafeWebhookUrlError, resolve_target


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
            targets, authority, hostname = await resolve_target(url)
            async with (
                httpx.AsyncClient(
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                asyncio.timeout(timeout_seconds),
            ):
                # Reserve connection time for every validated address.
                timeout = httpx.Timeout(
                    timeout_seconds, connect=timeout_seconds / len(targets)
                )
                for index, target in enumerate(targets):
                    try:
                        response = await client.post(
                            target,
                            content=body,
                            headers={
                                "Content-Type": "application/json",
                                **headers,
                                "Host": authority,
                            },
                            timeout=timeout,
                            extensions={"sni_hostname": hostname},
                        )
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        # These errors occur before HTTP headers/body are sent.
                        if index == len(targets) - 1:
                            raise
                    else:
                        break
        except (httpx.RequestError, UnsafeWebhookUrlError, TimeoutError) as error:
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
