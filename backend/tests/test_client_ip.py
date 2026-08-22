"""Whose address the rate limiter counts against.

Getting this wrong breaks the limiter in one of two ways, and both are
silent. Trust the header unconditionally and any client walks out of every
IP-keyed limit by sending one of its own. Trust it never and, behind Caddy,
every request in production carries the proxy's address -- so one class
tripping a limit locks out the whole site.
"""

from types import SimpleNamespace

from app.core.client_ip import client_ip


def _request(peer: str, forwarded: str | None = None):
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_direct_client_cannot_spoof_its_address():
    """The attack the trust check exists for: a client reaching the app
    directly claims to be somebody else, and would otherwise get a fresh
    quota for every value it invents."""
    assert client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_forwarded_header_is_read_from_a_trusted_proxy():
    assert client_ip(_request("172.18.0.5", "203.0.113.9")) == "203.0.113.9"


def test_client_prepended_entries_are_ignored():
    """A client may put anything in X-Forwarded-For before the proxy appends
    the real address, so the *right-most* untrusted entry is the honest one.
    Reading left-to-right would take the attacker's value every time."""
    assert client_ip(_request("172.18.0.5", "9.9.9.9, 203.0.113.9")) == "203.0.113.9"


def test_chained_proxies_are_skipped():
    """Two internal hops: both are ours, so the first public address to the
    left of them is the caller."""
    assert client_ip(_request("172.18.0.5", "203.0.113.9, 10.0.0.7, 172.18.0.5")) == "203.0.113.9"


def test_garbage_header_falls_back_to_the_peer():
    assert client_ip(_request("172.18.0.5", "not-an-ip")) == "172.18.0.5"
    assert client_ip(_request("172.18.0.5", "")) == "172.18.0.5"


def test_missing_header_from_a_proxy_falls_back_to_the_peer():
    assert client_ip(_request("172.18.0.5")) == "172.18.0.5"


def test_no_client_information_is_not_an_exception():
    """Starlette leaves `request.client` as None for some transports; the
    limiter must still get a key rather than raising inside a dependency."""
    assert client_ip(SimpleNamespace(client=None, headers={})) == "unknown"
