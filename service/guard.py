"""Request safety rules for the local API.

Three checks, shared by HTTP and WebSocket routes:

* Host: blocks DNS rebinding. A rebinding page has to use a registrable domain
  (evil.example), so only IP literals, single-label names (localhost, the PC's
  own name), Tailscale ``*.ts.net`` names and hosts listed in
  ``ORION_ALLOWED_HOSTS`` are accepted.
* Origin: blocks other websites. A browser always sends Origin on cross-site
  requests and WebSocket upgrades; it must match the Host, or be a localhost
  origin (the Vite dev server).
* Local: a request counts as "on this PC" only when it comes from loopback *and*
  no proxy forwarded it. ``tailscale serve`` proxies from 127.0.0.1, so those
  callers still need a paired device token.
"""

from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

LOOPBACK = {"127.0.0.1", "::1"}
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1"}
_PROXY_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "x-real-ip",
    "forwarded",
    "tailscale-user-login",
    "tailscale-user-name",
)


def _hostname(netloc: str) -> str:
    netloc = netloc.strip().lower()
    if not netloc:
        return ""
    if netloc.startswith("["):
        return netloc[1 : netloc.find("]")] if "]" in netloc else netloc
    if netloc.count(":") > 1:
        return netloc  # bare IPv6 without brackets
    return netloc.rsplit(":", 1)[0] if ":" in netloc else netloc


def _extra_hosts() -> set[str]:
    raw = os.environ.get("ORION_ALLOWED_HOSTS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def host_allowed(host_header: str | None) -> bool:
    name = _hostname(host_header or "")
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    if "." not in name:
        return True
    if name.endswith(".ts.net") or name.endswith(".localhost"):
        return True
    return name in _extra_hosts()


def origin_allowed(origin: str | None, host_header: str | None) -> bool:
    if not origin:
        return True  # native apps, curl, same-origin GET navigation
    if origin == "null":
        return False
    parts = urlsplit(origin)
    origin_host = _hostname(parts.netloc)
    if origin_host in _LOCAL_NAMES:
        return True
    return parts.netloc.lower() == (host_header or "").strip().lower()


def proxied(headers: Mapping[str, str]) -> bool:
    return any(headers.get(name) for name in _PROXY_HEADERS)


def is_local(client_host: str | None, headers: Mapping[str, str]) -> bool:
    return (client_host or "") in LOOPBACK and not proxied(headers)


def bearer(headers: Mapping[str, str]) -> str:
    return (headers.get("authorization") or "").removeprefix("Bearer ").strip()
