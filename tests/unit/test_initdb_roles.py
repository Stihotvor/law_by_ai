"""Static checks for the postgres init script that creates the three roles (rls-201 T1).

The live behaviour (pg_roles, pg_auth_members, SET ROLE) is checked by the
integration tests of T7/T8. These tests check the script and compose text.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docker" / "initdb" / "00-roles.sh"
COMPOSE = ROOT / "docker" / "docker-compose.yml"
ENV_EXAMPLE = ROOT / "docker" / ".env.example"
NEW_PASSWORDS = ("LAWBYAI_OWNER_PASSWORD", "LAWBYAI_APP_PASSWORD")


def _script() -> str:
    """Return the init script text."""
    return SCRIPT.read_text()


def _create_role(name: str) -> str:
    """Return the CREATE ROLE statement for one role, with whitespace collapsed."""
    match = re.search(rf"CREATE ROLE {name}\b[^;]*;", _script())
    assert match, f"no CREATE ROLE for {name}"
    return " ".join(match.group(0).split())


def _postgres_service() -> dict:
    """Return the postgres service from the compose file."""
    return yaml.safe_load(COMPOSE.read_text())["services"]["postgres"]


def test_roles_exist_with_the_right_attributes() -> None:
    """Scenario: Roles exist with the right attributes."""
    owner = _create_role("lawbyai_owner")
    app = _create_role("lawbyai_app")
    auth = _create_role("lawbyai_auth")
    for stmt in (owner, app, auth):
        assert "NOSUPERUSER" in stmt
        assert "NOCREATEDB" in stmt
    for stmt in (owner, app):
        assert " LOGIN" in stmt
        assert "NOBYPASSRLS" in stmt
    assert "NOLOGIN" in auth
    assert " BYPASSRLS" in auth
    for stmt in (app, auth):
        assert "NOINHERIT" in stmt
        assert "NOCREATEROLE" in stmt


def test_owner_can_build_and_set_the_function_owner() -> None:
    """Scenario: Owner can build and set the function owner."""
    text = " ".join(_script().split())
    assert "GRANT lawbyai_auth TO lawbyai_owner WITH INHERIT FALSE, SET TRUE;" in text
    assert "GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_owner;" in text
    # ALTER FUNCTION ... OWNER TO needs CREATE on the schema for the new owner.
    assert "GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_auth;" in text
    assert "GRANT USAGE ON SCHEMA public TO lawbyai_auth;" not in text


def test_app_cannot_reach_the_privileged_role() -> None:
    """Scenario: App cannot reach the privileged role (no membership is granted to it)."""
    text = " ".join(_script().split())
    grants = re.findall(r"GRANT lawbyai_auth TO (\w+)", text)
    assert grants == ["lawbyai_owner"]
    assert not re.search(r"GRANT \w+ TO lawbyai_app", text)


def test_no_password_in_the_repo() -> None:
    """Scenario: No password in the repo."""
    text = _script()
    assert not re.search(r"PASSWORD\s+'", text, re.IGNORECASE)
    assert not re.search(r"PASSWORD\s+\"", text, re.IGNORECASE)
    assert "change-me" not in text
    assert re.findall(r"PASSWORD\s+:'(\w+)'", text) == ["owner_password", "app_password"]
    assert "-v owner_password" not in text
    assert "-v app_password" not in text
    assert "\\getenv owner_password LAWBYAI_OWNER_PASSWORD" in text
    assert "\\getenv app_password LAWBYAI_APP_PASSWORD" in text
    for var in NEW_PASSWORDS:
        assert f"${{{var}:?" in text


def test_script_is_runnable_by_the_postgres_image() -> None:
    """Check that the script stops on errors and that uid 70 can read it.

    The entrypoint sources a non-executable `.sh` file, so the script must not
    change shell options that would leak into the entrypoint.
    """
    text = _script()
    assert text.startswith("#!/bin/sh")
    assert "ON_ERROR_STOP=1" in text
    assert not re.search(r"^set -", text, re.MULTILINE)
    assert SCRIPT.stat().st_mode & 0o004


def test_compose_passes_passwords_and_mounts_initdb() -> None:
    """Check that compose passes the two passwords and mounts the init scripts read-only."""
    svc = _postgres_service()
    for var in NEW_PASSWORDS:
        assert var in svc["environment"]
    assert "./initdb:/docker-entrypoint-initdb.d:ro" in svc["volumes"]


def test_env_example_has_change_me_passwords() -> None:
    """Check that the env example lists the two passwords with change-me values."""
    text = ENV_EXAMPLE.read_text()
    for var in NEW_PASSWORDS:
        assert re.search(rf"^{var}=change-me", text, re.MULTILINE), var
