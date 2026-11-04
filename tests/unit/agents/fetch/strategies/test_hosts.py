import socket
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from agents.fetch.errors import FetchTransportError, RedirectNotAllowedError, SourceConfigError
from agents.fetch.strategies._hosts import check_public_host, parse_base_url
from agents.fetch.strategies.rest_api import RestApiStrategy

SetDns = Callable[..., None]

PRIVATE = [
    "127.0.0.1",
    "10.0.0.5",
    "192.168.1.1",
    "169.254.1.1",
    "::1",
    ".".join(["0"] * 4),  # the unspecified IPv4 address
    "::ffff:127.0.0.1",
    "64:ff9b::7f00:1",
    "64:ff9b::a00:1",
    "2002:7f00:1::1",
    "2002:a00:1::",
]
EMBEDDED_PUBLIC = ["64:ff9b::808:808", "2002:808:808::"]


@pytest.mark.parametrize("addr", PRIVATE)
def test_private_resolution_rejected(set_dns: SetDns, addr: str) -> None:
    set_dns(addr)
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)
    check_public_host("h.example", allow_private=True)


def test_any_private_address_rejects(set_dns: SetDns) -> None:
    set_dns("8.8.8.8", "10.0.0.1")
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)


@pytest.mark.parametrize("addr", ["2606:4700::1%eth0", *EMBEDDED_PUBLIC])
def test_public_ipv6_allowed(set_dns: SetDns, addr: str) -> None:
    set_dns("8.8.8.8", addr)
    check_public_host("h.example", allow_private=False)


def test_empty_lookup_is_not_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", lambda *a, **k: [])
    with pytest.raises(SourceConfigError):
        check_public_host("h.example", allow_private=False)


@pytest.mark.parametrize("exc", [OSError("nx"), UnicodeError("bad label")])
def test_failed_lookup_is_transport_error(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def resolve(*args: Any, **kwargs: Any) -> Any:
        raise exc

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
    with pytest.raises(FetchTransportError):
        check_public_host("h.example", allow_private=False)


@pytest.mark.usefixtures("legacy_literal_dns")
@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "127.1"])
def test_legacy_literal_rejected(host: str) -> None:
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


def test_rest_resolves_only_the_source_host(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        seen.append(host)
        return [(2, 1, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://internal.example/x"})

    s = RestApiStrategy("https://api.example/v1", transport=httpx.MockTransport(handler))
    with pytest.raises(RedirectNotAllowedError):
        s._get_bytes("/x", None)
    assert seen == ["api.example"]


def test_rest_private_initial_host_rejected(set_dns: SetDns) -> None:
    set_dns("127.0.0.1")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x"))
    with pytest.raises(SourceConfigError):
        RestApiStrategy("https://api.example", transport=transport)._get_bytes("/x", None)
    ok = RestApiStrategy("https://api.example", transport=transport, allow_private_hosts=True)
    assert ok._get_bytes("/x", None) == b"x"


def test_rest_lookup_failure_is_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(*args: Any, **kwargs: Any) -> Any:
        raise OSError("nx")

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x"))
    with pytest.raises(FetchTransportError):
        RestApiStrategy("https://api.example", transport=transport)._get_bytes("/x", None)


def test_base_url_trailing_slashes_are_trimmed() -> None:
    assert parse_base_url("https://h.example/v1/").path == "/v1"
    assert parse_base_url("https://h.example//").path == ""


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("https://h.example:99999", "base_url is not a valid URL"),
        ("https://h.example?q=1", "base_url must not have a query or fragment"),
        ("https://h.example#f", "base_url must not have a query or fragment"),
    ],
)
def test_parse_base_url_messages(url: str, message: str) -> None:
    with pytest.raises(SourceConfigError) as err:
        parse_base_url(url)
    assert str(err.value) == message


def test_scope_suffix_is_cut_before_the_address_is_read(set_dns: SetDns) -> None:
    set_dns("2606:4700::1%")
    check_public_host("h.example", allow_private=False)


def test_lookup_asks_for_stream_addresses_of_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def resolve(*args: Any, **kwargs: Any) -> list[Any]:
        calls.append((args, kwargs))
        return [(2, 1, 6, "", ("8.8.8.8", 0))]

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
    check_public_host("h.example", allow_private=False)
    assert calls == [(("h.example", None), {"type": socket.SOCK_STREAM})]


def test_host_check_messages(monkeypatch: pytest.MonkeyPatch, set_dns: SetDns) -> None:
    set_dns("10.0.0.1")
    with pytest.raises(SourceConfigError) as private:
        check_public_host("h.example", allow_private=False)
    assert str(private.value) == "host is not public"

    def resolve(*args: Any, **kwargs: Any) -> Any:
        raise OSError("nx")

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
    with pytest.raises(FetchTransportError) as lookup:
        check_public_host("h.example", allow_private=False)
    assert str(lookup.value) == "host does not resolve"
