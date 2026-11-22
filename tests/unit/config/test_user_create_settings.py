import pytest

from config.settings import Settings

FIELDS = {
    "USER_CREATE_MAX": ("user_create_max", 10),
    "USER_CREATE_WINDOW_SECONDS": ("user_create_window_seconds", 3600),
}


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    # Keep a developer's local env file out of these tests.
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in FIELDS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("name", FIELDS)
def test_default(clean: pytest.MonkeyPatch, name: str) -> None:
    attr, default = FIELDS[name]
    value = getattr(Settings(), attr)
    assert value == default
    assert isinstance(value, int)


@pytest.mark.parametrize("name", FIELDS)
def test_override(clean: pytest.MonkeyPatch, name: str) -> None:
    clean.setenv(name, "2")
    assert getattr(Settings(), FIELDS[name][0]) == 2


@pytest.mark.parametrize("name", FIELDS)
@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_rejects_bad_values(clean: pytest.MonkeyPatch, name: str, value: str) -> None:
    clean.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        _ = getattr(Settings(), FIELDS[name][0])
