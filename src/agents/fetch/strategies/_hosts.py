"""Base URL and host rules shared by strategies."""

import ipaddress
import socket
from urllib.parse import SplitResult, urlsplit

from agents.fetch.errors import FetchTransportError, SourceConfigError

HTTPS_PORT = 443
_getaddrinfo = socket.getaddrinfo  # patchable resolver for tests


def parse_base_url(base_url: str) -> SplitResult:
    """Return the parsed URL, or raise if it is not a plain https URL with a host.

    Rejects other schemes, malformed ports, credentials, a missing host, and a
    query or fragment.
    """
    if not base_url.startswith("https://"):
        raise SourceConfigError("base_url must start with https://")
    try:
        parts = urlsplit(base_url.rstrip("/"))
        _ = parts.port
    except ValueError:
        raise SourceConfigError("base_url is not a valid URL") from None
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise SourceConfigError("base_url must not contain credentials")
    if not parts.hostname:
        raise SourceConfigError("base_url needs a host")
    if parts.query or parts.fragment:
        raise SourceConfigError("base_url must not have a query or fragment")
    return parts


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_6TO4 = ipaddress.ip_network("2002::/16")


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(ip.packed[12:])
    if ip in _6TO4:
        return ipaddress.IPv4Address(ip.packed[2:6])
    return None


def _is_global(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        return (_embedded_v4(ip) or ip).is_global
    return ip.is_global


def check_public_host(host: str, *, allow_private: bool) -> None:
    """Resolve ``host`` and reject it unless every address is globally routable.

    Raises ``FetchTransportError`` when the lookup fails and ``SourceConfigError``
    when an address is not public (the source points at an internal host).
    The resolver also reads legacy forms such as ``2130706433`` or ``127.1``.
    Addresses that embed IPv4 (mapped, NAT64, 6to4) count as public only if the
    embedded IPv4 is. Connections are not pinned to the checked address, so a
    DNS rebinding window remains between check and connect.
    """
    if allow_private:
        return
    try:
        infos = _getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise FetchTransportError("host does not resolve") from None
    if not infos or not all(_is_global(str(info[4][0])) for info in infos):
        raise SourceConfigError("host is not public")
