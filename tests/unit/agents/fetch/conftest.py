import socket
from collections.abc import Callable
from typing import Any

import pytest

SetDns = Callable[..., None]


def resolver(*addrs: str) -> Callable[..., list[Any]]:
    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", (a, 0)) for a in addrs]

    return resolve


@pytest.fixture
def set_dns(monkeypatch: pytest.MonkeyPatch) -> SetDns:
    """Make the host check resolve every name to the given addresses."""

    def install(*addrs: str) -> None:
        monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolver(*addrs))

    return install


@pytest.fixture(autouse=True)
def _public_dns(set_dns: SetDns) -> None:
    set_dns("93.184.216.34")


@pytest.fixture
def legacy_literal_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline stand-in that reads legacy IPv4 literals like the system resolver."""

    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", (socket.inet_ntoa(socket.inet_aton(host)), 0))]

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
