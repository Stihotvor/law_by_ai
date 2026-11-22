"""Domain errors and the import boundary of core.users."""

import subprocess
import sys
from pathlib import Path

import pytest

from core.users.errors import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
)

ERRORS: list[type[Exception]] = [
    UserCreateRefusedError,
    UserNotFoundError,
    SelfDeactivationError,
    LastAdminError,
]

SRC = Path(__file__).resolve().parents[4] / "src"

LIST_MODULES = "import sys, core.users; print('\\n'.join(sorted(sys.modules)))"


@pytest.mark.parametrize("error", ERRORS)
def test_errors_are_distinct_types(error: type[Exception]) -> None:
    assert issubclass(error, Exception)
    with pytest.raises(error) as caught:
        raise error("x")
    catchers = [other for other in ERRORS if isinstance(caught.value, other)]
    assert catchers == [error]


def test_package_keeps_import_boundary() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", LIST_MODULES],
        capture_output=True,
        check=True,
        cwd=SRC,
        text=True,
    )
    modules = result.stdout.split()
    assert "core.users" in modules
    bad = [m for m in modules if m.startswith("plugins") or m == "streamlit"]
    assert bad == []
