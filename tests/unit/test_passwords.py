import bcrypt
import pytest

from core.security.passwords import _DUMMY_HASH, check_password, hash_password


@pytest.mark.parametrize("hashed", ["", "not-a-hash", "$2b$12$short"])
def test_malformed_hash_returns_false(hashed: str) -> None:
    assert check_password("secret", hashed) is False


def test_dummy_hash_uses_same_rounds_as_real_hashes() -> None:
    assert _DUMMY_HASH[:7] == hash_password("x")[:7]
    assert bcrypt.checkpw(b"x", _DUMMY_HASH.encode()) is False


@pytest.mark.parametrize("plain", ["", "secret", "admin"])
def test_dummy_hash_never_matches(plain: str) -> None:
    assert check_password(plain, _DUMMY_HASH) is False


def test_hash_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    hashed = hash_password("secret")
    assert check_password("secret", hashed) is True
    assert check_password("wrong", hashed) is False
