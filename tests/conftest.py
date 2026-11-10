"""Shared pytest fixtures for the test suite.

The test tree is organised as ``tests/unit`` (pure, no external services),
``tests/integration`` (postgres/redis) and ``tests/e2e`` (whole stack).
Reusable construction helpers live in ``tests/factories``; shared fixtures in
``tests/fixtures``. See tests/README.md.
"""

import sys

import pytest

pytest_plugins = ["fixtures.plugins"]


@pytest.fixture(autouse=True)
def _clear_fake_fetch_records() -> None:
    """Empty the class-level lists the fake fetch strategies record into.

    Only tests that import the fakes load them, so other tests do not import the fetch package.
    """
    fakes = sys.modules.get("fakes.fetch")
    if fakes is not None:
        fakes.FakeStrategy.reads.clear()
        fakes.StaticFakeStrategy.reads.clear()
        fakes.StaticFakeStrategy.built_with.clear()
