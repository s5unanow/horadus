"""SSRF-safe, resource-bounded HTTP fetching for public-source collectors."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address

import httpx

from src.core.config import settings

IPAddress = IPv4Address | IPv6Address
AddressResolver = Callable[[str, int], Awaitable[tuple[IPAddress, ...]]]
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_STREAM_CHUNK_BYTES = 64 * 1024


class SafeFetchError(ValueError):
    """Base error for a collector fetch rejected by local safety policy."""


class UnsafeDestinationError(SafeFetchError):
    """Raised before connecting to a non-public or malformed destination."""


class ResponseTooLargeError(SafeFetchError):
    """Raised when a collector response exceeds its configured byte budget."""


@dataclass(frozen=True, slots=True)
class SafeFetchResponse:
    """Buffered response produced only after all safety and size checks pass."""

    url: httpx.URL
    status_code: int
    headers: httpx.Headers
    content: bytes
    encoding: str

    @property
    def text(self) -> str:
        """Decode the bounded response body with the server-selected encoding."""
        return self.content.decode(self.encoding, errors="replace")


def build_collector_fetcher(*, client: httpx.AsyncClient) -> SafeHTTPFetcher:
    """Build the shared collector fetch policy from validated application settings."""
    return SafeHTTPFetcher(
        client=client,
        max_response_bytes=settings.COLLECTOR_HTTP_MAX_RESPONSE_BYTES,
        max_redirects=settings.COLLECTOR_HTTP_MAX_REDIRECTS,
        connect_timeout_seconds=settings.COLLECTOR_HTTP_CONNECT_TIMEOUT_SECONDS,
        max_read_timeout_seconds=settings.COLLECTOR_HTTP_READ_TIMEOUT_SECONDS,
    )


async def resolve_host_addresses(host: str, port: int) -> tuple[IPAddress, ...]:
    """Resolve a host without blocking the event loop, preserving answer order."""
    try:
        return (ipaddress.ip_address(host),)
    except ValueError:
        pass

    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise httpx.ConnectError(f"Unable to resolve collector destination: {host}") from exc

    addresses = tuple(dict.fromkeys(ipaddress.ip_address(record[4][0]) for record in records))
    if not addresses:
        raise UnsafeDestinationError(f"Collector destination resolved no addresses: {host}")
    return addresses


class SafeHTTPFetcher:
    """Fetch public HTTP resources with address pinning and bounded buffering."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        max_response_bytes: int,
        max_redirects: int,
        connect_timeout_seconds: float = 10.0,
        max_read_timeout_seconds: float = 30.0,
        resolver: AddressResolver = resolve_host_addresses,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        if max_read_timeout_seconds <= 0:
            raise ValueError("max_read_timeout_seconds must be positive")
        self._client = client
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._connect_timeout_seconds = connect_timeout_seconds
        self._max_read_timeout_seconds = max_read_timeout_seconds
        self._resolver = resolver

    async def get(
        self,
        url: str | httpx.URL,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> SafeFetchResponse:
        """Fetch one URL, validating and pinning every bounded redirect hop."""
        current_url = httpx.URL(url)
        if params is not None:
            current_url = current_url.copy_merge_params(params)
        base_headers = httpx.Headers(headers)
        request_timeout = httpx.Timeout(
            connect=self._connect_timeout_seconds,
            read=min(timeout, self._max_read_timeout_seconds),
            write=self._connect_timeout_seconds,
            pool=self._connect_timeout_seconds,
        )

        for redirect_count in range(self._max_redirects + 1):
            pinned_url, request_headers, extensions = await self._pin_request(
                current_url,
                base_headers,
            )
            async with self._client.stream(
                "GET",
                pinned_url,
                headers=request_headers,
                timeout=request_timeout,
                follow_redirects=False,
                extensions=extensions,
            ) as response:
                location = response.headers.get("Location")
                if response.status_code in _REDIRECT_STATUSES and location is not None:
                    if redirect_count >= self._max_redirects:
                        raise SafeFetchError("Collector redirect limit exceeded")
                    current_url = current_url.join(location)
                    continue

                response.raise_for_status()
                content = await self._read_bounded_body(response)
                return SafeFetchResponse(
                    url=current_url,
                    status_code=response.status_code,
                    headers=httpx.Headers(response.headers),
                    content=content,
                    encoding=response.encoding or "utf-8",
                )

        raise RuntimeError("unreachable redirect loop state")

    async def _pin_request(
        self,
        url: httpx.URL,
        base_headers: httpx.Headers,
    ) -> tuple[httpx.URL, httpx.Headers, dict[str, str]]:
        scheme = url.scheme.lower()
        if scheme not in {"http", "https"}:
            raise UnsafeDestinationError("Collector URLs must use http or https")
        if not url.host:
            raise UnsafeDestinationError("Collector URL must include a hostname")
        if url.username or url.password:
            raise UnsafeDestinationError("Collector URLs must not include credentials")

        port = url.port or (443 if scheme == "https" else 80)
        addresses = await self._resolver(url.host, port)
        blocked = tuple(
            address for address in addresses if not address.is_global or address.is_multicast
        )
        if blocked:
            rendered = ", ".join(str(address) for address in blocked)
            raise UnsafeDestinationError(f"Collector destination is not public: {rendered}")
        if not addresses:
            raise UnsafeDestinationError("Collector destination resolved no addresses")

        request_headers = httpx.Headers(base_headers)
        request_headers["Host"] = url.netloc.decode("ascii")
        request_headers["Connection"] = "close"
        pinned_url = url.copy_with(host=str(addresses[0]))
        return (pinned_url, request_headers, {"sni_hostname": url.host})

    async def _read_bounded_body(self, response: httpx.Response) -> bytes:
        raw_content_length = response.headers.get("Content-Length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError as exc:
                raise SafeFetchError("Collector response has invalid Content-Length") from exc
            if content_length < 0 or content_length > self._max_response_bytes:
                raise ResponseTooLargeError("Collector response exceeds configured byte limit")

        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=_STREAM_CHUNK_BYTES):
            body.extend(chunk)
            if len(body) > self._max_response_bytes:
                raise ResponseTooLargeError("Collector response exceeds configured byte limit")
        return bytes(body)
