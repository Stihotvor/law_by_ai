"""Tests for core/plugins/exceptions.py (ADR-0001)."""

from core.plugins.exceptions import (
    PluginError,
    PluginLoadError,
    PluginNotFoundError,
    PluginValidationError,
)


def test_exception_hierarchy():
    assert issubclass(PluginLoadError, PluginError)
    assert issubclass(PluginNotFoundError, PluginError)
    assert issubclass(PluginValidationError, PluginError)


def test_instances_are_catchable_as_base():
    for exc in (
        PluginLoadError("x"),
        PluginNotFoundError("x"),
        PluginValidationError("x"),
    ):
        assert isinstance(exc, PluginError)
