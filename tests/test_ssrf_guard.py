"""check_employer fetches addresses a caller typed (an employer's domain, a page URL). On
the hosted endpoint that request leaves OUR network, so private, loopback, link-local and
cloud-metadata addresses must never be fetched, and a redirect must not smuggle one in."""

from __future__ import annotations

import socket

import pytest

from openhire.verify import checks


@pytest.mark.parametrize("url,reason", [
    ("http://127.0.0.1/", "private_ip"),
    ("http://[::1]/", "private_ip"),
    ("http://10.1.2.3/", "private_ip"),
    ("http://192.168.0.1/admin", "private_ip"),
    ("http://169.254.169.254/latest/meta-data/", "private_ip"),
    ("http://0.0.0.0/", "private_ip"),
    ("http://224.0.0.1/", "private_ip"),
    ("http://localhost/", "private_name"),
    ("http://db.internal/", "private_name"),
    ("http://printer.local/", "private_name"),
    ("http://intranet/", "private_name"),
    ("ftp://example.com/", "scheme"),
    ("file:///etc/passwd", "scheme"),
    ("http://example.com:8080/", "port"),
    ("http:///nohost", "no_host"),
])
def test_addresses_this_process_must_not_fetch(url, reason, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 80))])
    assert checks._blocked_reason(url) == reason


def test_public_name_resolving_to_a_private_address_is_blocked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.9.8.7", 443))])
    assert checks._blocked_reason("https://evil.example.com/") == "private_ip"


def test_public_name_resolving_publicly_passes(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("93.184.216.34", 443)), (10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0)),
    ])
    assert checks._blocked_reason("https://example.com/") is None


def test_unresolvable_name_is_left_to_the_request(monkeypatch):
    def gai(*a, **k):
        raise socket.gaierror("no such host")
    monkeypatch.setattr(socket, "getaddrinfo", gai)
    assert checks._blocked_reason("https://nonexistent.example.com/") is None


def test_get_never_calls_out_for_a_blocked_address(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("httpx.get must not be called for a private address")
    monkeypatch.setattr(checks.httpx, "get", forbidden)
    assert checks._get("http://127.0.0.1/") is None
    assert checks._get("http://169.254.169.254/") is None


def test_redirect_to_a_private_address_is_not_followed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    calls = []

    class R:
        def __init__(self, status, headers=None, text=""):
            self.status_code, self.headers, self.text = status, headers or {}, text

    def fake_get(url, **kw):
        calls.append(url)
        assert kw.get("follow_redirects") is False
        if url == "https://example.com/":
            return R(302, {"location": "http://169.254.169.254/latest/meta-data/"})
        return R(200, text="<html>never</html>")

    monkeypatch.setattr(checks.httpx, "get", fake_get)
    assert checks._get("https://example.com/") is None
    assert calls == ["https://example.com/"]


def test_public_redirects_are_followed_a_bounded_number_of_times(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])

    class R:
        def __init__(self, status, headers=None, text=""):
            self.status_code, self.headers, self.text = status, headers or {}, text

    hops = []

    def fake_get(url, **kw):
        hops.append(url)
        if url.endswith("/final"):
            return R(200, text="ok")
        return R(301, {"location": "/final"})

    monkeypatch.setattr(checks.httpx, "get", fake_get)
    r = checks._get("https://example.com/start")
    assert r is not None and r.text == "ok" and hops == ["https://example.com/start", "https://example.com/final"]

    hops.clear()
    monkeypatch.setattr(checks.httpx, "get", lambda url, **kw: hops.append(url) or R(302, {"location": url + "/x"}))
    assert checks._get("https://example.com/loop") is None
    assert len(hops) == checks._MAX_HOPS + 1


def test_homepage_check_of_a_private_address_is_reported_as_unreachable_not_as_a_fact(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("must not fetch")
    monkeypatch.setattr(checks.httpx, "get", forbidden)
    out = checks.homepage_check("127.0.0.1")
    assert out["status"] == "unavailable" and out["reason"] == "network"
