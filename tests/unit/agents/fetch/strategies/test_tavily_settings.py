import pytest

from config.settings import Settings

VARS = ("TAVILY_API_KEY", "TAVILY_TIMEOUT", "TAVILY_MAX_PAGES")


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()  # may load a repo .env, so clear the vars after construction
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    assert s.tavily_api_key == ""
    assert s.tavily_timeout == 60.0
    assert isinstance(s.tavily_timeout, float)
    assert s.tavily_max_pages == 20
    assert isinstance(s.tavily_max_pages, int)


def test_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("TAVILY_TIMEOUT", "12.5")
    monkeypatch.setenv("TAVILY_MAX_PAGES", "3")
    s = Settings()
    assert s.tavily_api_key == "k"
    assert s.tavily_timeout == 12.5
    assert s.tavily_max_pages == 3
