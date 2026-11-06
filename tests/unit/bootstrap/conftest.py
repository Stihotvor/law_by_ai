"""Shared fixtures for the init program tests."""

import logging

import pytest

from bootstrap import init_stack


@pytest.fixture(autouse=True)
def _capture_init_log(caplog: pytest.LogCaptureFixture) -> None:
    """Capture every log record of the init program."""
    caplog.set_level(logging.DEBUG, logger=init_stack.__name__)
