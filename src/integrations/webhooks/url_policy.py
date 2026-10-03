import asyncio
import ipaddress
import socket

import httpx


class UnsafeWebhookUrlError(ValueError):
    """A webhook target cannot be reached safely."""


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_reserved or address.is_multicast:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return address not in ipaddress.ip_network("192.0.0.0/24")
    # Block mapped/transition addresses that can route to embedded private IPv4.
    return not (
        address.is_site_local
        or address.ipv4_mapped is not None
        or address.sixtofour is not None
        or address.teredo is not None
        or address in ipaddress.ip_network("64:ff9b::/96")
        or address in ipaddress.ip_network("64:ff9b:1::/48")
    )


def validate_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise UnsafeWebhookUrlError("Invalid webhook URL") from error
    host = parsed.raw_host.decode("ascii")
    if parsed.scheme not in ("http", "https") or not host:
        raise UnsafeWebhookUrlError("Webhook URL must use HTTP or HTTPS")
    if parsed.username or parsed.password or "%" in host:
        raise UnsafeWebhookUrlError(
            "Webhook URL cannot contain credentials or a zone ID"
        )
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if host.rstrip(".").lower() == "localhost":
            raise UnsafeWebhookUrlError("Webhook URL must target a public address")
    else:
        if not public_address(host):
            raise UnsafeWebhookUrlError("Webhook URL must target a public address")
    return parsed


def _resolve(parsed: httpx.URL) -> list[str]:
    host = parsed.raw_host.decode("ascii")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            answers = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as error:
            raise UnsafeWebhookUrlError(
                "Webhook hostname could not be resolved"
            ) from error
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
    else:
        addresses = [host]
    if not addresses or any(not public_address(ip) for ip in addresses):
        raise UnsafeWebhookUrlError("Webhook URL must resolve only to public addresses")
    return addresses


async def resolve_target(url: str) -> tuple[list[httpx.URL], str, str]:
    parsed = validate_url(url)
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(_resolve, parsed), timeout=5
        )
    except TimeoutError as error:
        raise UnsafeWebhookUrlError("Webhook hostname resolution timed out") from error
    host = parsed.raw_host.decode("ascii")
    authority = f"[{host}]" if ":" in host else host
    if parsed.port is not None:
        authority += f":{parsed.port}"
    # The transport sees a literal IP, so it cannot resolve the domain again.
    return [parsed.copy_with(host=address) for address in addresses], authority, host
