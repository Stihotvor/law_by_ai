"""Domain errors of the user service.

``PrincipalRequiredError`` lives in ``core.security`` and is not redefined here.
"""


class UserCreateRefusedError(Exception):
    """Raised when a new user is rejected: duplicate email or invalid input."""


class UserCreateThrottledError(Exception):
    """Raised when the acting admin has created too many users in the current window."""


class UserNotFoundError(Exception):
    """Raised when the target user does not exist in the current tenant."""


class SelfDeactivationError(Exception):
    """Raised when an admin tries to deactivate their own account."""


class LastAdminError(Exception):
    """Raised when the change would leave the tenant without an active admin."""
