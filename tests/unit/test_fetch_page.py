"""Streamlit fetch page: role guard, submit, task status (no broker, no database)."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from celery.backends.asynchronous import E_RETRY_LIMIT_EXCEEDED
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from streamlit.testing.v1 import AppTest

from agents.fetch.sources import SOURCES
from tasks.celery_app import FETCH_DOCUMENT

PAGE = str(Path(__file__).resolve().parents[2] / "src" / "ui" / "pages" / "fetch.py")
EID = "DU/2024/1"


@pytest.fixture
def send_task() -> Iterator[MagicMock]:
    with patch("tasks.celery_app.app.send_task") as mock:
        mock.return_value.id = "task-1"
        yield mock


@contextmanager
def _async_result(state: str, result: Any = None) -> Iterator[MagicMock]:
    with patch("tasks.celery_app.app.AsyncResult") as mock:
        mock.return_value.state = state
        mock.return_value.result = result
        yield mock


@pytest.fixture
def pending() -> Iterator[MagicMock]:
    with _async_result("PENDING") as mock:
        yield mock


def _page(role: str | None) -> AppTest:
    at = AppTest.from_file(PAGE)
    if role is not None:
        at.session_state["user"] = {"role": role}
    return at.run()


def _submit(at: AppTest, external_id: str) -> AppTest:
    at.text_input[0].input(external_id)
    at.button[0].click()
    return at.run()


def _text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in [*at.markdown, *at.info, *at.success, *at.code])


def test_admin_submit_sends_task_with_source_and_id(
    send_task: MagicMock, pending: MagicMock
) -> None:
    at = _submit(_page("admin"), f"  {EID}  ")
    send_task.assert_called_once_with(FETCH_DOCUMENT, args=[SOURCES.names()[0], EID])
    assert at.session_state["fetch_task_id"] == "task-1"


def test_broker_down_shows_one_error_and_stores_no_task_id(send_task: MagicMock) -> None:
    send_task.side_effect = OperationalError("broker down")
    at = _submit(_page("admin"), EID)
    assert len(at.error) == 1
    assert "fetch_task_id" not in at.session_state


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (RedisConnectionError("backend down"), "Task queue is not available. Try again later."),
        (
            RuntimeError(E_RETRY_LIMIT_EXCEEDED),
            "Task result store is not reachable. Restart the Celery services.",
        ),
    ],
)
def test_backend_down_on_submit_shows_one_error_and_stores_no_task_id(
    send_task: MagicMock, error: Exception, message: str
) -> None:
    send_task.side_effect = error
    at = _submit(_page("admin"), EID)
    assert [e.value for e in at.error] == [message]
    assert "fetch_task_id" not in at.session_state


def test_other_runtime_error_from_send_task_propagates(send_task: MagicMock) -> None:
    send_task.side_effect = RuntimeError("unrelated bug")
    at = _submit(_page("admin"), EID)
    assert at.exception
    assert "unrelated bug" in at.exception[0].message
    assert len(at.error) == 0
    assert "fetch_task_id" not in at.session_state


def test_backend_down_on_status_shows_error_and_keeps_refresh(send_task: MagicMock) -> None:
    with patch("tasks.celery_app.app.AsyncResult") as mock:
        type(mock.return_value).state = PropertyMock(
            side_effect=RedisConnectionError("backend down")
        )
        at = _submit(_page("admin"), EID)
    assert [e.value for e in at.error] == ["Task status is not available. Try again later."]
    assert "task-1" in _text(at)
    assert any(b.label == "Refresh status" for b in at.button)


def test_page_does_not_import_task_module() -> None:
    tree = ast.parse(Path(PAGE).read_text(encoding="utf-8"))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "tasks.fetch" not in modules


@pytest.mark.parametrize("external_id", ["", "   "])
def test_blank_id_shows_error_and_does_not_call_task(
    send_task: MagicMock, external_id: str
) -> None:
    at = _submit(_page("admin"), external_id)
    assert len(at.error) == 1
    send_task.assert_not_called()


@pytest.mark.parametrize("role", ["user", None])
def test_non_admin_has_no_submit_button(send_task: MagicMock, role: str | None) -> None:
    at = _page(role)
    assert len(at.button) == 0
    assert len(at.warning) == 1
    send_task.assert_not_called()


@pytest.mark.parametrize(
    ("state", "result", "expected"),
    [
        ("PENDING", None, "PENDING"),
        ("SUCCESS", {"status": "saved"}, "saved"),
        ("SUCCESS", {"status": "skipped"}, "skipped"),
    ],
)
def test_status_shows_task_state_and_result_status(
    send_task: MagicMock, state: str, result: Any, expected: str
) -> None:
    with _async_result(state, result) as mock:
        at = _submit(_page("admin"), EID)
        mock.assert_called_with("task-1")
        mock.return_value.get.assert_not_called()
        assert "task-1" in _text(at)
        assert expected in _text(at)


def test_invalid_result_shows_one_error(send_task: MagicMock) -> None:
    with _async_result("SUCCESS", {"status": "invalid", "external_id": "x"}):
        at = _submit(_page("admin"), EID)
    assert [e.value for e in at.error] == ["Invalid document id for this source."]


def test_unsupported_result_shows_one_error(send_task: MagicMock) -> None:
    with _async_result("SUCCESS", {"status": "unsupported", "external_id": "x"}):
        at = _submit(_page("admin"), EID)
    assert [e.value for e in at.error] == ["This source does not support fetch by id."]


def test_refresh_status_shows_new_state(send_task: MagicMock) -> None:
    with _async_result("PENDING") as mock:
        at = _submit(_page("admin"), EID)
        assert "PENDING" in _text(at)
        mock.return_value.state = "SUCCESS"
        mock.return_value.result = {"status": "saved"}
        refresh = next(b for b in at.button if b.label == "Refresh status")
        at = refresh.click().run()
        assert "SUCCESS" in _text(at)
        assert "saved" in _text(at)
        mock.return_value.get.assert_not_called()
