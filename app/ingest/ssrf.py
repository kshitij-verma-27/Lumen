import ipaddress
import logging
import socket
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Disallowed IP networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),         # Current network
    ipaddress.ip_network("10.0.0.0/8"),        # Private network
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local (includes cloud metadata 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),     # Private network
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),    # Private network
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),   # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),    # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved
    ipaddress.ip_network("255.255.255.255/32"),# Broadcast
    # IPv6 blocked ranges
    ipaddress.ip_network("::/128"),            # Unspecified
    ipaddress.ip_network("::1/128"),           # Loopback
    ipaddress.ip_network("fc00::/7"),          # Unique local address
    ipaddress.ip_network("fe80::/10"),         # Link-local unicast
    ipaddress.ip_network("ff00::/8"),          # Multicast
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
}


def is_ip_blocked(ip_str: str) -> Tuple[bool, Optional[str]]:
    """Checks if an IP string falls into a blocked or private network range."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for net in BLOCKED_NETWORKS:
            if ip in net:
                return True, f"IP {ip_str} falls into blocked range {net}"
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return True, f"IP {ip_str} is private, loopback, or reserved"
        return False, None
    except ValueError:
        return True, f"Invalid IP address format: {ip_str}"


def is_url_safe(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validates a URL against SSRF vulnerabilities:
    - Scheme must be http or https
    - Hostname must resolve to a valid, non-private public IP address
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid"

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Could not parse URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Disallowed scheme '{parsed.scheme}'. Only http and https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing hostname"

    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES or hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
        return False, f"Blocked private hostname: {hostname}"

    # Check if hostname is already a direct IP
    try:
        direct_ip = ipaddress.ip_address(hostname_lower)
        blocked, reason = is_ip_blocked(str(direct_ip))
        if blocked:
            return False, f"Direct IP blocked: {reason}"
        return True, None
    except ValueError:
        # Not a direct IP, need DNS resolution
        pass

    # By default and in live mode, ssrf.py strictly fails closed.
    # Synthetic domain bypass is only active if explicitly enabled via LUMEN_ALLOW_TEST_DOMAINS=true (off by default).
    import os
    allow_test_domains = os.environ.get("LUMEN_ALLOW_TEST_DOMAINS", "").lower() == "true"

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False, f"Hostname '{hostname}' did not resolve to any IP address"

        resolved_ips = {item[4][0] for item in addr_info}
        for ip_str in resolved_ips:
            blocked, reason = is_ip_blocked(ip_str)
            if blocked:
                logger.warning(f"SSRF blocked: Hostname '{hostname}' resolved to blocked IP '{ip_str}' ({reason})")
                return False, f"SSRF blocked: Hostname resolved to forbidden IP ({reason})"

        return True, None
    except socket.gaierror as e:
        if allow_test_domains:
            logger.info(f"Test environment: allowing unresolved synthetic domain '{hostname}' under LUMEN_ALLOW_TEST_DOMAINS")
            return True, None
        return False, f"DNS resolution failed for hostname '{hostname}': {e}"
    except Exception as e:
        return False, f"Security check error: {e}"
