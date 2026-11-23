"""Error hierarchy of core.llm."""

from core.llm.errors import LLMConfigError, LLMError, LLMTimeoutError


def test_error_hierarchy() -> None:
    assert issubclass(LLMTimeoutError, LLMError)
    assert not issubclass(LLMConfigError, LLMError)
    assert LLMError("x", 503).status_code == 503
    assert LLMError("x").status_code is None
