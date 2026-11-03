import pytest

from agents.fetch.errors import SourceConfigError
from agents.fetch.strategies._hosts import check_public_host
from agents.fetch.strategies.rest_api import RestApiStrategy
from agents.fetch.strategies.tavily import TavilyCrawlStrategy

BAD = [
    "localhost",
    "LOCALHOST.",
    "127.0.0.1",
    "10.0.0.5",
    "192.168.1.1",
    "169.254.1.1",
    "::1",
    "0.0.0.0",
]


@pytest.mark.parametrize("host", BAD)
def test_private_hosts_rejected(host: str) -> None:
    with pytest.raises(SourceConfigError):
        check_public_host(host, allow_private=False)
    check_public_host(host, allow_private=True)


@pytest.mark.parametrize("host", ["example.com", "8.8.8.8"])
def test_public_hosts_allowed(host: str) -> None:
    check_public_host(host, allow_private=False)


def test_rest_strategy_rejects_and_opts_in() -> None:
    with pytest.raises(SourceConfigError):
        RestApiStrategy("https://127.0.0.1:8443/api")
    RestApiStrategy("https://127.0.0.1:8443/api", allow_private_hosts=True)


def test_tavily_strategy_rejects_and_opts_in() -> None:
    from unittest.mock import MagicMock

    with pytest.raises(SourceConfigError):
        TavilyCrawlStrategy("https://10.0.0.1/", client=MagicMock())
    TavilyCrawlStrategy("https://10.0.0.1/", client=MagicMock(), allow_private_hosts=True)
