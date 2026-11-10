"""Unit tests for the smoke worker bootstrap: mock Sejm handler and host-guard patch."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agents.fetch.registry import Registry
from agents.fetch.sources.sejm_eli import SejmEliSource
from agents.fetch.strategies import rest_api
from agents.fetch.strategies.base import FetchStrategy
from smoke import worker_bootstrap as wb

FIXTURES = Path(__file__).parent / "fixtures"
META_URL = "https://api.sejm.gov.pl/eli/acts/DU/2024/1"
TEXT_URL = META_URL + "/text.html"


@pytest.fixture
def handler() -> wb.Handler:
    return wb.make_handler(wb.load_fixtures(FIXTURES))


def test_meta_path_returns_the_meta_fixture(handler: wb.Handler) -> None:
    response = handler(httpx.Request("GET", META_URL))
    assert response.status_code == 200
    assert response.content == (FIXTURES / "du_2024_1_meta.json").read_bytes()


def test_text_path_returns_the_html_fixture(handler: wb.Handler) -> None:
    response = handler(httpx.Request("GET", TEXT_URL))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.content == (FIXTURES / "du_2024_1_text.html").read_bytes()


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "https://api.sejm.gov.pl/eli/acts/DU/2024/2"),
        ("POST", META_URL),
        ("GET", "https://example.com/eli/acts/DU/2024/1"),
    ],
)
def test_anything_else_returns_404(handler: wb.Handler, method: str, url: str) -> None:
    assert handler(httpx.Request(method, url)).status_code == 404


def test_missing_fixture_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        wb.install_sejm_mock(tmp_path)


def test_host_check_skips_only_the_sejm_host(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        wb,
        "_real_check_public_host",
        lambda host, *, allow_private: calls.append((host, allow_private)),
    )
    wb.check_public_host("api.sejm.gov.pl", allow_private=False)
    wb.check_public_host("example.com", allow_private=False)
    assert calls == [("example.com", False)]


def test_install_routes_sejm_eli_through_the_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    monkeypatch.setattr(wb, "STRATEGIES", strategies)
    monkeypatch.setattr(SejmEliSource, "strategy_name", SejmEliSource.strategy_name)
    monkeypatch.setattr(rest_api, "check_public_host", rest_api.check_public_host)
    wb.install_sejm_mock(FIXTURES)
    strategy = strategies.get(SejmEliSource.strategy_name)(SejmEliSource.base_url)
    assert isinstance(strategy, rest_api.RestApiStrategy)
    meta = strategy.get_meta(strategy.make_ref("sejm_eli", "DU/2024/1"))
    expected = json.loads((FIXTURES / "du_2024_1_meta.json").read_text(encoding="utf-8"))
    assert meta.title == expected["title"]


def test_main_installs_the_mock_then_starts_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(wb, "install_sejm_mock", calls.append)
    monkeypatch.setattr(wb.app, "worker_main", calls.append)
    with pytest.raises(SystemExit):
        wb.main()
    assert calls == [wb.FIXTURES_DIR, ["worker", "--loglevel=info", "--concurrency=2"]]
