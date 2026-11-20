import bcrypt
import pytest

from core.security.passwords import DUMMY_HASH, check_password, hash_password


@pytest.mark.parametrize("hashed", ["", "not-a-hash", "$2b$12$short"])
def test_malformed_hash_returns_false(hashed: str) -> None:
    assert check_password("secret", hashed) is False


def test_dummy_hash_uses_same_rounds_as_real_hashes() -> None:
    assert DUMMY_HASH[:7] == hash_password("x")[:7]
    assert bcrypt.checkpw(b"x", DUMMY_HASH.encode()) is False


@pytest.mark.parametrize("plain", ["", "secret", "admin"])
def test_dummy_hash_never_matches(plain: str) -> None:
    assert check_password(plain, DUMMY_HASH) is False


def test_hash_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    hashed = hash_password("secret")
    assert check_password("secret", hashed) is True
    assert check_password("wrong", hashed) is False


def test_password_limits_live_in_core() -> None:
    from bootstrap import init_stack
    from core.security import passwords

    assert (passwords.MIN_PASSWORD_CHARS, passwords.MAX_PASSWORD_BYTES) == (12, 72)
    assert init_stack.MIN_PASSWORD_CHARS is passwords.MIN_PASSWORD_CHARS
    assert init_stack.MAX_PASSWORD_BYTES is passwords.MAX_PASSWORD_BYTES
