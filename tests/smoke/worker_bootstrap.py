"""Start the Celery worker with a mocked Sejm ELI API (Docker smoke test only).

docker/docker-compose.smoke.yml runs this file instead of the worker command.
The mock is installed before the worker starts, so prefork children inherit it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import httpx

from agents.fetch.sources.sejm_eli import SejmEliSource
from agents.fetch.strategies import rest_api
from agents.fetch.strategies._hosts import check_public_host as _real_check_public_host
from agents.fetch.strategies.base import STRATEGIES
from tasks.celery_app import app

Handler = Callable[[httpx.Request], httpx.Response]

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SEJM_HOST = "api.sejm.gov.pl"
STRATEGY_NAME = "smoke_rest_api"
# Same args as the celery-worker `command` in docker/docker-compose.yml.
WORKER_ARGV = ["worker", "--loglevel=info", "--concurrency=2"]
_ROUTES = {
    "/eli/acts/DU/2024/1": ("du_2024_1_meta.json", "application/json"),
    "/eli/acts/DU/2024/1/text.html": ("du_2024_1_text.html", "text/html; charset=utf-8"),
}


def load_fixtures(fixtures_dir: Path) -> dict[str, tuple[bytes, str]]:
    """Map each mocked path to its body and content type; raise FileNotFoundError if absent."""
    return {
        path: ((fixtures_dir / name).read_bytes(), mime) for path, (name, mime) in _ROUTES.items()
    }


def make_handler(bodies: dict[str, tuple[bytes, str]]) -> Handler:
    """Return a handler that serves *bodies* for GET on the Sejm host and 404 otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve the fixture for a known GET path on the Sejm host; else 404."""
        hit = bodies.get(request.url.path)
        if request.method != "GET" or request.url.host != SEJM_HOST or hit is None:
            return httpx.Response(404)
        return httpx.Response(200, content=hit[0], headers={"content-type": hit[1]})

    return handler


def check_public_host(host: str, *, allow_private: bool) -> None:
    """Skip the DNS check for the mocked Sejm host; keep it for every other host."""
    if host == SEJM_HOST:
        return
    _real_check_public_host(host, allow_private=allow_private)


def install_sejm_mock(fixtures_dir: Path) -> None:
    """Route the ``sejm_eli`` source through a REST strategy with a mock transport."""
    transport = httpx.MockTransport(make_handler(load_fixtures(fixtures_dir)))

    class SmokeRestApiStrategy(rest_api.RestApiStrategy):
        """REST strategy that sends every request through the mock transport."""

        def __init__(self, base_url: str, *, allow_private_hosts: bool = False) -> None:
            """Build the strategy with the mock transport injected."""
            super().__init__(base_url, transport=transport, allow_private_hosts=allow_private_hosts)

    STRATEGIES.register(STRATEGY_NAME)(SmokeRestApiStrategy)
    SejmEliSource.strategy_name = STRATEGY_NAME
    rest_api.check_public_host = check_public_host


def main() -> NoReturn:
    """Install the Sejm mock, then run the Celery worker."""
    install_sejm_mock(FIXTURES_DIR)
    app.worker_main(WORKER_ARGV)
    raise SystemExit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
