from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("agents.fetch.strategies._hosts._getaddrinfo", resolve)
