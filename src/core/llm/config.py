"""Resolve one frozen LLM config per agent from Settings."""

import math
from dataclasses import dataclass
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

    base_url: str
    model: str
    timeout: float
    api_key: str


def resolve(settings: Settings, agent_name: str) -> AgentLLMConfig:
    """Build the config for ``agent_name``: per-agent value, else global value."""
    if agent_name not in LLM_AGENTS:
        raise LLMConfigError(f"unknown LLM agent {agent_name!r}")
    model = settings.llm_setting("model", agent_name)
    if not model:
        var = f"LLM_MODEL_{agent_name.upper()}"
        raise LLMConfigError(f"no LLM model for agent {agent_name!r}: set {var} or LLM_MODEL")
    base_url = settings.llm_setting("base_url", agent_name)
    _check_base_url(base_url, agent_name)
    return AgentLLMConfig(
        base_url=base_url,
        model=model,
        timeout=_timeout(settings, agent_name),
        api_key=settings.llm_setting("api_key", agent_name),
    )


def _timeout(settings: Settings, agent_name: str) -> float:
    """Per-agent timeout, else the validated global ``llm_timeout``."""
    fallback = settings.llm_timeout
    raw = settings.llm_setting("timeout", agent_name).strip()
    if not raw:
        return fallback
    var = f"LLM_TIMEOUT_{agent_name.upper()}"
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{var} must be a number, got {raw!r}") from None
    if not (value > 0 and math.isfinite(value)):
        raise ValueError(f"{var} must be positive and finite, got {raw!r}")
    return value


def _check_base_url(base_url: str, agent_name: str) -> None:
    """Reject an empty URL, credentials, query, fragment or a non-http(s) scheme.

    The message names the agent but never the URL, which may hold secrets.
    """
    parts = urlsplit(base_url)
    bad = (
        not parts.netloc
        or parts.scheme not in ("http", "https")
        or "@" in parts.netloc
        or parts.query
        or parts.fragment
    )
    if bad:
        raise LLMConfigError(f"invalid or missing LLM base URL for agent {agent_name!r}")
