"""Settings that the init program reads."""

import pytest

from config.settings import Settings

INIT_VARS = {
    "INIT_TENANT_ID": ("init_tenant_id", "platform"),
    "INIT_TENANT_NAME": ("init_tenant_name", "Platform"),
    "INIT_ADMIN_EMAIL": ("init_admin_email", ""),
    "INIT_ADMIN_NAME": ("init_admin_name", "Admin"),
    "INIT_ADMIN_PASSWORD": ("init_admin_password", ""),
}


@pytest.mark.parametrize(("var", "attr_default"), INIT_VARS.items())
def test_init_settings_default_and_env(
    var: str, attr_default: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    attr, default = attr_default
    monkeypatch.delenv(var, raising=False)
    settings = Settings()
    monkeypatch.delenv(var, raising=False)
    assert getattr(settings, attr) == default
    monkeypatch.setenv(var, "from-env")
    assert getattr(settings, attr) == "from-env"
