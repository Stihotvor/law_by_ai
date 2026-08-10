"""Shared type aliases for plugin protocols (ADR-0001)."""

from typing import Any

# JSON-compatible plugin payloads; refined by concrete implementations.
JsonDict = dict[str, Any]


__all__ = ["JsonDict"]
