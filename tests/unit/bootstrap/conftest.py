import logging

import pytest

from bootstrap import init_stack


@pytest.fixture(autouse=True)
def _capture_init_log(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=init_stack.__name__)
