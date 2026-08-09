"""Plugin-specific errors (ADR-0001)."""


class PluginError(Exception):
    """Base class for all plugin errors."""


class PluginNotFoundError(PluginError):
    """A plugin of the requested type is not registered."""


class PluginLoadError(PluginError):
    """A registered plugin module or class could not be imported/instantiated."""


class PluginValidationError(PluginError):
    """A registered plugin does not satisfy its protocol."""


__all__ = [
    "PluginError",
    "PluginLoadError",
    "PluginNotFoundError",
    "PluginValidationError",
]
