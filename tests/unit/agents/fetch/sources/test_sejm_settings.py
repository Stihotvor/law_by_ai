import pytest

from config.settings import Settings


def test_default(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    monkeypatch.delenv("SEJM_MIN_INTERVAL", raising=False)
    assert s.sejm_min_interval == 0.5
    assert isinstance(s.sejm_min_interval, float)


def test_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEJM_MIN_INTERVAL", "2")
    value = Settings().sejm_min_interval
    assert value == 2.0
    assert isinstance(value, float)
