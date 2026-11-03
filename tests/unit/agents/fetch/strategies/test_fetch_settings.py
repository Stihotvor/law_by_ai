import pytest

from config.settings import Settings

VARS = (
    "FETCH_HTTP_TIMEOUT",
    "FETCH_TOTAL_TIMEOUT",
    "FETCH_MAX_BYTES",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "MINIO_SECURE",
)


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _fresh(mp: pytest.MonkeyPatch) -> Settings:
    s = Settings()  # may load a repo .env, so clear the vars after construction
    for name in VARS:
        mp.delenv(name, raising=False)
    return s


def test_defaults(clean: pytest.MonkeyPatch) -> None:
    s = _fresh(clean)
    assert s.fetch_http_timeout == 10.0
    assert isinstance(s.fetch_http_timeout, float)
    assert s.fetch_total_timeout == 60.0
    assert s.fetch_max_bytes == 52428800
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_bucket == "legal-documents"
    assert s.minio_secure is True


def test_overrides(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("FETCH_HTTP_TIMEOUT", "2.5")
    clean.setenv("FETCH_MAX_BYTES", "7")
    clean.setenv("FETCH_TOTAL_TIMEOUT", "9")
    clean.setenv("MINIO_ENDPOINT", "h:1")
    clean.setenv("MINIO_ACCESS_KEY", "a")
    clean.setenv("MINIO_SECRET_KEY", "s")
    clean.setenv("MINIO_BUCKET", "b")
    clean.setenv("MINIO_SECURE", "false")
    s = Settings()
    assert s.fetch_http_timeout == 2.5
    assert s.fetch_max_bytes == 7
    assert s.fetch_total_timeout == 9.0
    assert s.minio_endpoint == "h:1"
    assert s.minio_access_key == "a"
    assert s.minio_secret_key == "s"
    assert s.minio_bucket == "b"
    assert s.minio_secure is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", " On "])
def test_secure_truthy(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("MINIO_SECURE", value)
    assert Settings().minio_secure is True


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_secure_falsy(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("MINIO_SECURE", value)
    assert Settings().minio_secure is False


def test_keys_default_empty(clean: pytest.MonkeyPatch) -> None:
    s = _fresh(clean)
    assert s.minio_access_key == ""
    assert s.minio_secret_key == ""


@pytest.mark.parametrize(
    ("name", "attr"),
    [
        ("FETCH_HTTP_TIMEOUT", "fetch_http_timeout"),
        ("FETCH_TOTAL_TIMEOUT", "fetch_total_timeout"),
        ("FETCH_MAX_BYTES", "fetch_max_bytes"),
    ],
)
@pytest.mark.parametrize("value", ["0", "-1", "abc", "nan", "inf"])
def test_fetch_limits_must_be_positive_finite(
    clean: pytest.MonkeyPatch, name: str, attr: str, value: str
) -> None:
    clean.setenv(name, value)
    s = Settings()
    with pytest.raises(ValueError, match=name):
        _ = getattr(s, attr)
