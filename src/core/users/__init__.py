"""User management core: domain errors and the store port.

Imports only ``core.security`` and own modules. No ``plugins.*``, no ``streamlit``.
"""

from .errors import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserCreateThrottledError,
    UserNotFoundError,
)
from .ports import CreateRateLimiter, UserRecord, UserRepository
from .service import UserService

__all__ = [
    "CreateRateLimiter",
    "LastAdminError",
    "SelfDeactivationError",
    "UserCreateRefusedError",
    "UserCreateThrottledError",
    "UserNotFoundError",
    "UserRecord",
    "UserRepository",
    "UserService",
]
