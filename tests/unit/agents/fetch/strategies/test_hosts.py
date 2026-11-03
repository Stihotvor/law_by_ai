from typing import Any

import httpx
import pytest

from agents.fetch.errors import SourceConfigError
from agents.fetch.strategies._hosts import check_public_host, parse_base_url
from agents.fetch.strategies.rest_api import RestApiStrategy

PRIVATE = [
    "127.0.0.1",
    "10.0.0.5",
    "192.168.1.1",
    "169.254.1.1",
    "::1",
    "0.0.0.0",
    "::ffff:127.0.0.1",
]


def _resolver(*addrs: str) -> Any:
    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", (a, 0)) for a in addrs]

    return resolve


@pytest.mark.parametrize("addr", PRIVATE)
def test_private_resolution_rejected(monkeypatch: pytest.MonkeyPatch, addr: str) -> None:
    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", _resolver(addr))
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)
    check_public_host("h.example", allow_private=True)


def test_any_private_address_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.fetch.strategies._hosts._getaddrinfo", _resolver("8.8.8.8", "10.0.0.1")
    )
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)


def test_public_and_scoped_ipv6_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.fetch.strategies._hosts._getaddrinfo", _resolver("8.8.8.8", "2606:4700::1%eth0")
    )
    check_public_host("h.example", allow_private=False)


@pytest.mark.parametrize("result", [[], OSError("nx")])
def test_lookup_failure_rejected(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    def resolve(*args: Any, **kwargs: Any) -> Any:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)


def test_real_resolver_reads_legacy_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", socket.getaddrinfo)
    for host in ("2130706433", "0x7f000001", "127.1"):
        with pytest.raises(SourceConfigError):
            check_public_host(host, allow_private=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://x",
        "https://u:p@x",
        "https://u@x",
        "https://",
        "https://x?q=1",
        "https://x#f",
        "https://x:99999",
    ],
)
def test_parse_base_url_rejects(url: str) -> None:
    with pytest.raises(SourceConfigError):
        parse_base_url(url)


def test_rest_checks_host_per_request_and_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        seen.append(host)
        return [(2, 1, 6, "", ("10.0.0.1" if host == "internal.example" else "8.8.8.8", 0))]

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://internal.example/x"})

    s = RestApiStrategy("https://api.example/v1", transport=httpx.MockTransport(handler))
    with pytest.raises(SourceConfigError):
        s._get_bytes("/x", None)
    assert seen[0] == "api.example"


def test_rest_private_initial_host_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", _resolver("127.0.0.1"))
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x"))
    with pytest.raises(SourceConfigError):
        RestApiStrategy("https://api.example", transport=transport)._get_bytes("/x", None)
    ok = RestApiStrategy("https://api.example", transport=transport, allow_private_hosts=True)
    assert ok._get_bytes("/x", None) == b"x"
