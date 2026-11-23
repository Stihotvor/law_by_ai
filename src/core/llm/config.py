"""Resolve one frozen LLM config per agent from Settings."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from config.settings import Settings
from core.llm.errors import LLMConfigError

LLM_AGENTS: tuple[str, ...] = (
    "document_fetcher",
    "document_processor",
    "legal_research",
    "change_tracker",
    "knowledge_graph",
    "analysis",
    "bureaucracy_assistant",
)


@dataclass(frozen=True)
class AgentLLMConfig:
    """LLM endpoint settings for one agent."""

    base_url: str = field(repr=False)
    model: str
    timeout: float
    api_key: str = field(repr=False)


def resolve(settings: Settings, agent_name: str) -> AgentLLMConfig:
    """Build the config for ``agent_name``: per-agent value, else global value."""
    if agent_name not in LLM_AGENTS:
        raise LLMConfigError(f"unknown LLM agent {agent_name!r}")
    model = settings.llm_setting("model", agent_name)
    if not model:
        var = settings.llm_var_name("model", agent_name)
        fallback = settings.llm_var_name("model", None)
        raise LLMConfigError(f"no LLM model for agent {agent_name!r}: set {var} or {fallback}")
    base_url = settings.llm_setting("base_url", agent_name)
    _check_base_url(base_url, agent_name)
    return AgentLLMConfig(
        base_url=base_url,
        model=model,
        timeout=settings.llm_agent_timeout(agent_name),
        api_key=settings.llm_setting("api_key", agent_name),
    )


def _check_base_url(base_url: str, agent_name: str) -> None:
    """Reject a bad base URL; the message names the agent but never the URL.

    The URL may hold secrets, so it is not echoed.
    """
    if not _is_valid_base_url(base_url):
        raise LLMConfigError(f"invalid or missing LLM base URL for agent {agent_name!r}")


def _is_valid_base_url(base_url: str) -> bool:
    """Require http(s), a hostname, a valid port, no credentials, query or fragment."""
    try:
        parts = urlsplit(base_url)
        _ = parts.port
    except ValueError:
        return False
    return (
        bool(parts.hostname)
        and parts.scheme in ("http", "https")
        and "@" not in parts.netloc
        and not parts.query
        and not parts.fragment
    )
