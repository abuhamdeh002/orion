"""How a phone reaches this PC: an explicit ORION_PUBLIC_URL, or this PC's Tailscale name."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

_cache: tuple[float, str | None] = (0.0, None)


def _tailscale() -> str | None:
    found = shutil.which("tailscale")
    if found:
        return found
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
    return str(default) if default.is_file() else None


def tailscale_name() -> str | None:
    """This PC's MagicDNS name (pc.tailnet.ts.net) while Tailscale is running, else None. Cached 60 s."""
    global _cache
    checked, name = _cache
    if time.monotonic() - checked < 60:
        return name
    name = None
    executable = _tailscale()
    if executable:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0  # type: ignore[attr-defined]
        try:
            done = subprocess.run(
                [executable, "status", "--json"], capture_output=True, text=True, timeout=4, creationflags=flags
            )
            status = json.loads(done.stdout or "{}")
            dns = str((status.get("Self") or {}).get("DNSName") or "").rstrip(".")
            if status.get("BackendState") == "Running" and dns.endswith(".ts.net"):
                name = dns
        except (OSError, subprocess.SubprocessError, ValueError):
            name = None
    _cache = (time.monotonic(), name)
    return name


def public_base(config) -> str | None:
    """The address a phone should open, without a trailing slash, or None when nothing reaches this PC."""
    explicit = (getattr(config, "orion_public_url", None) or "").strip().rstrip("/")
    if explicit:
        return explicit
    name = tailscale_name()
    return f"https://{name}" if name else None


UNREACHABLE = (
    "Your phone can't reach this PC yet. Install Tailscale on both, then run "
    "'tailscale serve --bg 8765' on the PC and pair again. Or set ORION_PUBLIC_URL."
)
