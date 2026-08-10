"""Shared pytest fixtures for the test suite.

The test tree is organised as ``tests/unit`` (pure, no external services),
``tests/integration`` (postgres/redis) and ``tests/e2e`` (whole stack).
Reusable construction helpers live in ``tests/factories``; shared fixtures in
``tests/fixtures``. See tests/README.md.
"""

pytest_plugins = ["fixtures.plugins"]
