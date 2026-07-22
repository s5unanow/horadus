from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest

from src.ingestion.safe_http import (
    ResponseTooLargeError,
    SafeFetchError,
    SafeHTTPFetcher,
    UnsafeDestinationError,
    resolve_host_addresses,
)

pytestmark = pytest.mark.unit

_PUBLIC_V4 = ipaddress.ip_address("93.184.216.34")
_SECOND_PUBLIC_V4 = ipaddress.ip_address("1.1.1.1")


async def _public_resolver(_host: str, _port: int):
    return (_PUBLIC_V4,)


class _ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_safe_fetch_pins_public_ip_and_preserves_host_and_sni() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, headers={"Content-Type": "text/plain; charset=utf-8"}, content=b"ok"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=2,
            max_read_timeout_seconds=3,
            resolver=_public_resolver,
        )
        response = await fetcher.get(
            "https://example.com/source?existing=1",
            params={"added": "2"},
            headers={"User-Agent": "test"},
            timeout=5,
        )

    assert response.text == "ok"
    assert str(response.url) == "https://example.com/source?existing=1&added=2"
    assert len(seen) == 1
    assert seen[0].url.host == str(_PUBLIC_V4)
    assert seen[0].headers["Host"] == "example.com"
    assert seen[0].headers["Connection"] == "close"
    assert seen[0].headers["User-Agent"] == "test"
    assert seen[0].extensions["sni_hostname"] == "example.com"
    assert seen[0].extensions["timeout"]["connect"] == 10.0
    assert seen[0].extensions["timeout"]["read"] == 3


@pytest.mark.asyncio
async def test_safe_fetch_revalidates_and_repins_redirect_host() -> None:
    resolved_hosts: list[str] = []
    seen: list[tuple[str, str]] = []

    async def resolver(host: str, _port: int):
        resolved_hosts.append(host)
        return (_PUBLIC_V4,) if host == "first.example" else (_SECOND_PUBLIC_V4,)

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers["Host"]))
        if request.headers["Host"] == "first.example":
            return httpx.Response(302, headers={"Location": "https://second.example/final"})
        return httpx.Response(200, content=b"redirected")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=2,
            resolver=resolver,
        ).get("https://first.example/start", timeout=5)

    assert response.content == b"redirected"
    assert resolved_hosts == ["first.example", "second.example"]
    assert seen == [
        (str(_PUBLIC_V4), "first.example"),
        (str(_SECOND_PUBLIC_V4), "second.example"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_address",
    [
        "10.0.0.1",
        "127.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "192.0.2.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
    ],
)
async def test_safe_fetch_rejects_non_public_or_mixed_resolution_before_request(
    blocked_address: str,
) -> None:
    handler = AsyncMock()

    async def mixed_resolver(_host: str, _port: int):
        return (_PUBLIC_V4, ipaddress.ip_address(blocked_address))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=2,
            resolver=mixed_resolver,
        )
        with pytest.raises(UnsafeDestinationError, match="not public"):
            await fetcher.get("https://mixed.example/", timeout=5)

    handler.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("file:///etc/passwd", "http or https"),
        ("http:///missing-host", "hostname"),
        (
            httpx.URL("https://example.com/").copy_with(username="test-user"),
            "credentials",
        ),
    ],
)
async def test_safe_fetch_rejects_malformed_or_credentialed_urls(
    url: str | httpx.URL,
    message: str,
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(AsyncMock())) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=0,
            resolver=_public_resolver,
        )
        with pytest.raises(UnsafeDestinationError, match=message):
            await fetcher.get(url, timeout=5)


@pytest.mark.asyncio
async def test_safe_fetch_enforces_redirect_limit_and_http_status() -> None:
    async def redirect_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"Location": "/again"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=0,
            resolver=_public_resolver,
        )
        with pytest.raises(SafeFetchError, match="redirect limit"):
            await fetcher.get("https://example.com/start", timeout=5)

    async def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(error_handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=100,
            max_redirects=1,
            resolver=_public_resolver,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await fetcher.get("https://example.com/failed", timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "stream"),
    [
        ({"Content-Length": "101"}, _ChunkStream(b"small")),
        ({}, _ChunkStream(b"123456", b"78901")),
    ],
)
async def test_safe_fetch_caps_declared_and_streamed_response_size(
    headers: dict[str, str],
    stream: httpx.AsyncByteStream,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, headers=headers, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=10,
            max_redirects=1,
            resolver=_public_resolver,
        )
        with pytest.raises(ResponseTooLargeError, match="byte limit"):
            await fetcher.get("https://example.com/large", timeout=5)


@pytest.mark.asyncio
async def test_safe_fetch_rejects_invalid_length_and_empty_resolution() -> None:
    async def invalid_length_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, headers={"Content-Length": "invalid"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid_length_handler)) as client:
        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=10,
            max_redirects=1,
            resolver=_public_resolver,
        )
        with pytest.raises(SafeFetchError, match="invalid Content-Length"):
            await fetcher.get("https://example.com/invalid", timeout=5)

        fetcher = SafeHTTPFetcher(
            client=client,
            max_response_bytes=10,
            max_redirects=1,
            resolver=AsyncMock(return_value=()),
        )
        with pytest.raises(UnsafeDestinationError, match="resolved no addresses"):
            await fetcher.get("https://example.com/empty", timeout=5)


def test_safe_fetch_validates_constructor_limits() -> None:
    client = AsyncMock(spec=httpx.AsyncClient)
    with pytest.raises(ValueError, match="max_response_bytes"):
        SafeHTTPFetcher(client=client, max_response_bytes=0, max_redirects=1)
    with pytest.raises(ValueError, match="max_redirects"):
        SafeHTTPFetcher(client=client, max_response_bytes=1, max_redirects=-1)
    with pytest.raises(ValueError, match="max_read_timeout_seconds"):
        SafeHTTPFetcher(
            client=client,
            max_response_bytes=1,
            max_redirects=1,
            max_read_timeout_seconds=0,
        )


@pytest.mark.asyncio
async def test_resolve_host_addresses_handles_literals_dns_dedup_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await resolve_host_addresses("127.0.0.1", 80) == (ipaddress.ip_address("127.0.0.1"),)

    loop = asyncio.get_running_loop()
    getaddrinfo = AsyncMock(
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        ]
    )
    monkeypatch.setattr(loop, "getaddrinfo", getaddrinfo)
    assert await resolve_host_addresses("example.com", 443) == (_PUBLIC_V4,)

    getaddrinfo.side_effect = socket.gaierror("failed")
    with pytest.raises(httpx.ConnectError, match="Unable to resolve"):
        await resolve_host_addresses("failed.example", 443)

    getaddrinfo.side_effect = None
    getaddrinfo.return_value = []
    with pytest.raises(UnsafeDestinationError, match="resolved no addresses"):
        await resolve_host_addresses("empty.example", 443)
