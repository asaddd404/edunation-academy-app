"""Resolving the real caller address behind a reverse proxy.

Every request in production arrives from Caddy, so `request.client.host` is
the proxy's own address for all of them -- an IP-keyed rate limit built on it
either never fires or blocks the whole site at once.

The forwarded header can only be believed when the *immediate* peer is a
proxy we run: anyone can send `X-Forwarded-For: 1.2.3.4` straight at the app
and step out of every IP limit otherwise. So the header is read only when the
socket peer is inside `trusted_proxy_cidrs`, and then only its right-most
entry that isn't itself a trusted proxy -- the left-hand entries are
attacker-controlled (a client may prepend its own).
"""

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.config import settings


@lru_cache(maxsize=1)
def _trusted_networks() -> tuple:
    """Parsed once: this runs on every rate-limited request, and re-parsing
    the CIDR list each time is pure waste."""
    return tuple(settings.trusted_proxy_networks)


def _parse(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(address) -> bool:
    return any(address in network for network in _trusted_networks())


def client_ip(request: Request) -> str:
    peer_raw = request.client.host if request.client else ""
    peer = _parse(peer_raw)
    if peer is None:
        return peer_raw or "unknown"
    if not _is_trusted(peer):
        # Direct connection: the socket address is the truth, and any
        # forwarded header on it is the client's own invention.
        return str(peer)

    forwarded = request.headers.get("x-forwarded-for", "")
    for candidate_raw in reversed(forwarded.split(",")):
        candidate = _parse(candidate_raw)
        if candidate is None:
            continue
        if _is_trusted(candidate):
            continue
        return str(candidate)

    return str(peer)
