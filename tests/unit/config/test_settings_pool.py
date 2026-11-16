import pytest

from config.settings import PoolConfig, Settings

# env name -> (property, default, a valid override, a rejected value)
FIELDS: dict[str, tuple[str, int, str, str]] = {
    "POSTGRES_POOL_SIZE": ("postgres_pool_size", 5, "1", "0"),
    "POSTGRES_MAX_OVERFLOW": ("postgres_max_overflow", 10, "0", "-1"),
    "WORKER_POSTGRES_POOL_SIZE": ("worker_postgres_pool_size", 1, "2", "abc"),
    "WORKER_POSTGRES_MAX_OVERFLOW": ("worker_postgres_max_overflow", 1, "0", "-1"),
}


# Scenario: Defaults
def test_defaults(clean_pool_env: pytest.MonkeyPatch) -> None:
    settings = Settings()
    assert settings.app_pool_config() == PoolConfig(5, 10)
    assert settings.worker_pool_config() == PoolConfig(1, 1)


# Scenario: Valid override
def test_valid_override(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("WORKER_POSTGRES_POOL_SIZE", "2")
    clean_pool_env.setenv("POSTGRES_MAX_OVERFLOW", "0")
    settings = Settings()
    assert settings.worker_postgres_pool_size == 2
    assert settings.postgres_max_overflow == 0


# Scenario: Empty value uses the default
def test_empty_value_uses_default(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("POSTGRES_POOL_SIZE", "")
    assert Settings().postgres_pool_size == 5


# Scenario Outline: Rejected value
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("POSTGRES_POOL_SIZE", "0"),
        ("POSTGRES_MAX_OVERFLOW", "-1"),
        ("WORKER_POSTGRES_POOL_SIZE", "abc"),
        ("WORKER_POSTGRES_MAX_OVERFLOW", "-1"),
    ],
)
def test_rejected_value(clean_pool_env: pytest.MonkeyPatch, name: str, value: str) -> None:
    clean_pool_env.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        _ = getattr(Settings(), FIELDS[name][0])


# Scenario: PoolConfig validates itself
@pytest.mark.parametrize(("size", "max_overflow"), [(0, 1), (1, -1)])
def test_pool_config_validates_itself(size: int, max_overflow: int) -> None:
    with pytest.raises(ValueError, match="pool"):
        PoolConfig(size, max_overflow)


# Per-setting coverage: default, valid override, rejected value.
@pytest.mark.parametrize("name", FIELDS)
def test_each_default(clean_pool_env: pytest.MonkeyPatch, name: str) -> None:
    attr, default, _, _ = FIELDS[name]
    value = getattr(Settings(), attr)
    assert value == default
    assert isinstance(value, int)


@pytest.mark.parametrize("name", FIELDS)
def test_each_override(clean_pool_env: pytest.MonkeyPatch, name: str) -> None:
    attr, _, override, _ = FIELDS[name]
    clean_pool_env.setenv(name, override)
    assert getattr(Settings(), attr) == int(override)


@pytest.mark.parametrize("name", FIELDS)
@pytest.mark.parametrize("value", ["-5", "1.5", "x"])
def test_each_rejects(clean_pool_env: pytest.MonkeyPatch, name: str, value: str) -> None:
    clean_pool_env.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        _ = getattr(Settings(), FIELDS[name][0])
