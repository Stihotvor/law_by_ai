import socket
from typing import Any, NoReturn

import pytest

import agents.fetch.sources.sejm_eli as sejm


class RecordingThrottle:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def wait(self) -> None:
        self.log.append("wait")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FETCH_HTTP_TIMEOUT", "3.5")
    monkeypatch.setenv("FETCH_MAX_BYTES", "100000")


@pytest.fixture
def events() -> list[str]:
    return []


@pytest.fixture
def no_throttle(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> list[str]:
    monkeypatch.setattr(sejm, "_THROTTLE", RecordingThrottle(events))
    return events
