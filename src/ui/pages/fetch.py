"""Fetch page: an admin queues one document fetch and checks the task status."""

from __future__ import annotations

import streamlit as st
from kombu.exceptions import OperationalError

from agents.fetch.sources import SOURCES
from tasks.celery_app import FETCH_DOCUMENT, app
from ui.components.auth import require_admin

TASK_KEY = "fetch_task_id"
_ERRORS = {
    "invalid": "Invalid document id for this source.",
    "unsupported": "This source does not support fetch by id.",
}


def _queue(source: str, external_id: str) -> None:
    """Send the fetch task and store its id; show an error if the broker is down."""
    try:
        result = app.send_task(FETCH_DOCUMENT, args=[source, external_id])
    except OperationalError:
        st.error("Task queue is not available. Try again later.")
        return
    st.session_state[TASK_KEY] = result.id


def _submit_form() -> None:
    """Show the fetch form and queue the task on submit."""
    with st.form("fetch"):
        source = st.selectbox("Source", SOURCES.names())
        external_id = st.text_input("Document id (for example DU/2024/1)").strip()
        submitted = st.form_submit_button("Fetch")
    if not submitted:
        return
    if not external_id:
        st.error("Enter a document id.")
        return
    _queue(source, external_id)


def _show_status(task_id: str) -> None:
    """Show the task state without waiting for the result."""
    result = app.AsyncResult(task_id)
    st.markdown(f"Task `{task_id}`: **{result.state}**")
    if result.state == "SUCCESS" and isinstance(result.result, dict):
        status = result.result.get("status")
        if status in _ERRORS:
            st.error(_ERRORS[status])
        else:
            st.markdown(f"Result: **{status}**")
    st.button("Refresh status")


st.title("Fetch a document")
require_admin()
_submit_form()
if TASK_KEY in st.session_state:
    _show_status(st.session_state[TASK_KEY])
