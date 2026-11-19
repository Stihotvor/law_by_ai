"""QA gap tests for auth-login-ui: cases not covered by the existing tests."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.security.rbac import PrivilegeEscalationError, check_privilege_escalation, is_admin
from ui.components import auth

ROOT = Path(__file__).resolve().parents[2]
STALE = ("ADR-0004", "token_store")


def test_qa_004_none_role_fails_closed() -> None:
    assert is_admin(None) is False  # type: ignore[arg-type]
    with pytest.raises(PrivilegeEscalationError):
        check_privilege_escalation(None)  # type: ignore[arg-type]


def test_qa_010_denied_user_stays_denied() -> None:
    for _ in range(4):
        with pytest.raises(PrivilegeEscalationError):
            check_privilege_escalation("user")


class _Stopped(Exception):
    pass


def test_qa_018_session_edit_alone_does_not_grant_admin() -> None:
    st = MagicMock()
    st.session_state = {
        auth.USERNAME_KEY: "carol@x.com|1",
        auth.EXPIRES_KEY: time.time() + 3600,
        auth.LOGOUT_KEY: False,
    }
    st.stop.side_effect = _Stopped
    row: dict[str, Any] = {
        "id": "u-9",
        "tenant_id": "t-1",
        "email": "carol@x.com",
        "name": "Carol",
        "role": "user",
        "password_hash": "x",
        "is_active": True,
        "session_version": 1,
    }
    with (
        patch.object(auth, "st", st),
        patch.object(auth, "set_current_tenant"),
        patch.object(auth, "reset_current_tenant"),
        patch.object(auth, "get_settings", MagicMock()),
        patch.object(auth, "CookieModel", MagicMock()),
        patch.object(auth, "_lookup", lambda email: row),
        patch.object(auth, "_cookie_sent", lambda name: False),
        patch.object(auth, "logout_button"),
        patch.object(auth, "login_form"),
    ):
        auth.require_auth()
        st.session_state[auth.SESSION_USER_KEY]["role"] = "admin"  # tampering
        auth.require_auth()
        with pytest.raises(_Stopped):
            auth.require_admin()
        assert st.session_state[auth.SESSION_USER_KEY]["role"] == "user"
        st.warning.assert_called_with("Admin role required.")


def _scan(paths: list[Path]) -> list[str]:
    hits = []
    for p in paths:
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{p}:{s}" for s in STALE if s in text]
    return hits


def test_qa_027_no_stale_text_in_core_security() -> None:
    files = [p for p in (ROOT / "src/core/security").rglob("*") if "__pycache__" not in p.parts]
    assert _scan(files) == []


def test_qa_028_no_stale_text_in_readmes() -> None:
    readmes = [
        ROOT / "src/core/README.md",
        ROOT / "src/core/security/README.md",
        ROOT / "src/ui/README.md",
        ROOT / "tests/README.md",
    ]
    assert _scan(readmes) == []


def test_qa_029_security_text_cites_current_adrs() -> None:
    text = "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (ROOT / "src/core/security").rglob("*")
        if p.suffix in {".py", ".md"}
    )
    assert "ADR-0013" in text
    assert "ADR-0003" in text


def test_qa_030_pyjwt_exact_pin() -> None:
    lines = [
        ln
        for ln in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if "pyjwt" in ln.lower()
    ]
    assert len(lines) == 1
    assert re.search(r'"pyjwt==\d+\.\d+\.\d+"', lines[0])
    assert not re.search(r"[<>~!]=?|>=", lines[0].split("pyjwt", 1)[1].replace("==", ""))
