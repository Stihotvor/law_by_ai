"""Port for chat models, so agents can use a fake in tests."""

from typing import Protocol


class ChatModel(Protocol):
    """Sends chat messages for one agent and returns the reply text."""

    def chat(self, agent_name: str, messages: list[dict[str, str]]) -> str:
        """Return the model reply for ``messages``."""
        ...  # pragma: no cover
