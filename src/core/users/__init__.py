"""User management core: domain errors and the store port.

Imports only ``core.security`` and own modules. No ``plugins.*``, no ``streamlit``.
"""

from .errors import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
)
from .ports import UserRecord, UserRepository

__all__ = [
    "LastAdminError",
    "SelfDeactivationError",
    "UserCreateRefusedError",
    "UserNotFoundError",
    "UserRecord",
    "UserRepository",
]
