"""Per-agent LLM config resolver and the ChatModel port."""

import os

import pytest

from config.settings import Settings
from core.llm.config import LLM_AGENTS, AgentLLMConfig, resolve
from core.llm.errors import LLMConfigError
from core.llm.ports import ChatModel

_AGENT = "bureaucracy_assistant"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No env file and no LLM variables; returns the monkeypatch to set them."""
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    return monkeypatch


def _set_agent(env: pytest.MonkeyPatch, agent: str, **values: str) -> None:
    for field, value in values.items():
        env.setenv(f"LLM_{field.upper()}_{agent.upper()}", value)


def test_llm_agents_match_settings() -> None:
    prefix = "llm_model_"
    names = {n.removeprefix(prefix) for n in dir(Settings) if n.startswith(prefix)}
    assert set(LLM_AGENTS) == names
    assert len(LLM_AGENTS) == 7


def test_per_agent_value_wins(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_BASE_URL", "http://g:2/v1")
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="5", api_key="k-a")
    config = resolve(Settings(), _AGENT)
    assert config == AgentLLMConfig(
        base_url="http://a:1/v1", model="m-a", timeout=5.0, api_key="k-a"
    )


def test_global_value_is_fallback(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_BASE_URL", "https://g:2/v1")
    env.setenv("LLM_MODEL", "m-g")
    env.setenv("LLM_TIMEOUT", "7")
    env.setenv("LLM_API_KEY", "k-g")
    config = resolve(Settings(), "document_processor")
    assert config == AgentLLMConfig(
        base_url="https://g:2/v1", model="m-g", timeout=7.0, api_key="k-g"
    )


def test_unknown_agent(env: pytest.MonkeyPatch) -> None:
    with pytest.raises(LLMConfigError, match="nope"):
        resolve(Settings(), "nope")


def test_no_model(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_BASE_URL", "http://g:2/v1")
    with pytest.raises(LLMConfigError) as info:
        resolve(Settings(), "document_processor")
    assert "document_processor" in str(info.value)
    assert "LLM_MODEL_DOCUMENT_PROCESSOR" in str(info.value)


def test_bad_per_agent_timeout(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="0")
    with pytest.raises(ValueError, match="LLM_TIMEOUT_BUREAUCRACY_ASSISTANT"):
        resolve(Settings(), _AGENT)


def test_empty_base_url(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, model="m-a")
    with pytest.raises(LLMConfigError, match=_AGENT):
        resolve(Settings(), _AGENT)


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pw@host/v1",
        "http://host/v1?x=1",
        "http://host/v1#frag",
        "ftp://host/v1",
        "http://:80/v1",
        "http://host:99999/v1",
        "http://host:port/v1",
        "http://[::1/v1",
    ],
)
def test_bad_base_url(env: pytest.MonkeyPatch, url: str) -> None:
    _set_agent(env, _AGENT, base_url=url, model="m-a")
    with pytest.raises(LLMConfigError) as info:
        resolve(Settings(), _AGENT)
    assert _AGENT in str(info.value)
    assert url not in str(info.value)


class _FakeChat:
    def chat(self, agent_name: str, messages: list[dict[str, str]]) -> str:
        return f"{agent_name}:{len(messages)}"


def test_fake_satisfies_port() -> None:
    model: ChatModel = _FakeChat()
    assert model.chat("analysis", [{"role": "user", "content": "hi"}]) == "analysis:1"


def test_default_timeout_when_unset(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a")
    assert resolve(Settings(), _AGENT).timeout == 60.0


def test_non_numeric_per_agent_timeout(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="soon")
    with pytest.raises(ValueError, match="LLM_TIMEOUT_BUREAUCRACY_ASSISTANT"):
        resolve(Settings(), _AGENT)


def test_repr_hides_key_and_url(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, base_url="http://secret-host:1/v1", model="m-a", api_key="k-secret")
    text = repr(resolve(Settings(), _AGENT))
    assert "k-secret" not in text
    assert "secret-host" not in text
    assert "m-a" in text


def test_timeout_error_does_not_echo_value(env: pytest.MonkeyPatch) -> None:
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="soon-xyz")
    with pytest.raises(ValueError, match="LLM_TIMEOUT_BUREAUCRACY_ASSISTANT") as info:
        resolve(Settings(), _AGENT)
    assert "soon-xyz" not in str(info.value)


def test_bad_global_timeout_does_not_break_valid_agent_timeout(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_TIMEOUT", "abc")
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="5")
    assert resolve(Settings(), _AGENT).timeout == 5.0


def test_bad_global_timeout_used_when_agent_timeout_empty(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_TIMEOUT", "abc")
    _set_agent(env, _AGENT, base_url="http://a:1/v1", model="m-a", timeout="")
    with pytest.raises(ValueError, match="LLM_TIMEOUT") as info:
        resolve(Settings(), _AGENT)
    assert "LLM_TIMEOUT_" not in str(info.value)
