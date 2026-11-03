"""Host rules shared by strategies that connect to a ``base_url``."""

import ipaddress

from agents.fetch.errors import SourceConfigError


def check_public_host(host: str, *, allow_private: bool) -> None:
    """Reject ``localhost`` and loopback, link-local or private IP literals."""
    if allow_private:
        return
    if host.lower().rstrip(".") == "localhost":
        raise SourceConfigError("base_url host is not public")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_unspecified:
        raise SourceConfigError("base_url host is not public")
