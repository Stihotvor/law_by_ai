import pytest

from config.settings import Settings

VARS = ("AUTH_COOKIE_KEY", "AUTH_COOKIE_NAME", "AUTH_COOKIE_EXPIRY_DAYS")


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    # Keep a developer's .env file out of these tests.
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_cookie_key_missing(clean: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="AUTH_COOKIE_KEY"):
        _ = Settings().auth_cookie_key


@pytest.mark.parametrize("value", ["", "k" * 31, "some_key"])
def test_cookie_key_rejected(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("AUTH_COOKIE_KEY", value)
    with pytest.raises(ValueError, match="AUTH_COOKIE_KEY") as exc:
        _ = Settings().auth_cookie_key
    if value:
        assert value not in str(exc.value)


def test_cookie_key_valid(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("AUTH_COOKIE_KEY", "k" * 32)
    assert Settings().auth_cookie_key == "k" * 32


def test_cookie_name_default(clean: pytest.MonkeyPatch) -> None:
    assert Settings().auth_cookie_name == "law_by_ai_auth"


def test_cookie_name_override(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("AUTH_COOKIE_NAME", "c")
    assert Settings().auth_cookie_name == "c"


def test_expiry_default(clean: pytest.MonkeyPatch) -> None:
    days = Settings().auth_cookie_expiry_days
    assert days == 30
    assert isinstance(days, int)


def test_expiry_override(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("AUTH_COOKIE_EXPIRY_DAYS", "7")
    assert Settings().auth_cookie_expiry_days == 7


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_expiry_rejects_bad_values(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("AUTH_COOKIE_EXPIRY_DAYS", value)
    with pytest.raises(ValueError, match="AUTH_COOKIE_EXPIRY_DAYS"):
        _ = Settings().auth_cookie_expiry_days
