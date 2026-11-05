"""Offline license. A missing key is a 14-day trial.

What each state allows:
* Trial (14 days) and any valid license: everything.
* Lifetime license: everything on the PC plus phone access over your own network; the cloud relay needs a cloud plan.
* Expired (trial over, bad or lapsed key): chat, voice, and tools on the PC keep working.
  Phone access (paired devices, pairing new ones) and the cloud relay stop.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.paths import app_data_dir

# Public half of the license signing key (rotated 2026-11-04). The private half lives only in the
# site's LICENSE_PRIVATE_HEX secret (cloud/site/.dev.vars locally, a Worker secret in production).
_PUBLIC_RAW = bytes.fromhex("667f4a50d0936e33bd257b4fd3d318cc3a926b5a6c7279c64a761ea000747b95")
TRIAL_SECONDS = 14 * 24 * 60 * 60
_CACHE_SECONDS = 60.0


@dataclass
class LicenseState:
    plan: str
    cloud: bool
    expires_at: int | None
    reason: str

    @property
    def allows_cloud(self) -> bool:
        return self.cloud and self.plan != "expired"

    @property
    def allows_phone(self) -> bool:
        return self.plan != "expired"

    @property
    def notice(self) -> str | None:
        if self.plan != "expired":
            return None
        return (
            f"{self.reason} Chat and voice on this PC keep working. "
            "Phone access and the cloud relay need a license."
        )


TRIAL_ENDED_DETAIL = "Your ORION trial has ended. Phone access needs a license; ORION still works on the PC itself."


def public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_PUBLIC_RAW)


def set_public_key(raw: bytes) -> None:
    global _PUBLIC_RAW
    if len(raw) != 32:
        raise ValueError("Ed25519 public key is 32 bytes.")
    _PUBLIC_RAW = raw


def sign_license(payload: dict, private_raw: bytes) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = Ed25519PrivateKey.from_private_bytes(private_raw).sign(body)
    return _b64(body) + "." + _b64(signature)


def verify_license(token: str, now: float | None = None) -> LicenseState:
    moment = int(now if now is not None else time.time())
    try:
        encoded_body, encoded_signature = token.split(".", 1)
        body = _b64decode(encoded_body)
        public_key().verify(_b64decode(encoded_signature), body)
        payload = json.loads(body)
    except Exception:
        return LicenseState("expired", False, None, "The license key is not valid.")
    expires = payload.get("exp")
    if isinstance(expires, int) and expires < moment:
        return LicenseState("expired", False, expires, "The license has expired.")
    plan = str(payload.get("plan") or "lifetime")
    return LicenseState(plan, bool(payload.get("cloud")), expires if isinstance(expires, int) else None, "Licensed.")


def current_license(path: Path | None = None, now: float | None = None) -> LicenseState:
    moment = now if now is not None else time.time()
    key_path = path or (app_data_dir() / "license.key")
    if key_path.exists():
        return verify_license(key_path.read_text(encoding="utf-8").strip(), moment)
    # The registry copy only applies to the real install, never to a test's temporary folder.
    trial = _trial_start(key_path.parent, moment, use_registry=path is None)
    if moment - trial < TRIAL_SECONDS:
        return LicenseState("trial", True, int(trial + TRIAL_SECONDS), "Trial.")
    return LicenseState("expired", False, int(trial + TRIAL_SECONDS), "The trial has ended.")


_cached: tuple[float, LicenseState] | None = None


def license_gate() -> LicenseState:
    """current_license(), read at most once a minute. Used on every remote request."""
    global _cached
    if _cached is not None and time.monotonic() - _cached[0] < _CACHE_SECONDS:
        return _cached[1]
    state = current_license()
    _cached = (time.monotonic(), state)
    return state


def forget_cached_license() -> None:
    global _cached
    _cached = None


_TRIAL_KEY = r"Software\ORION"
_TRIAL_VALUE = "TrialStart"


def _registry_trial() -> float | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _TRIAL_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, _TRIAL_VALUE)
        return float(value)
    except (ImportError, OSError, ValueError):
        return None


def _save_registry_trial(start: float) -> None:
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _TRIAL_KEY) as key:
            winreg.SetValueEx(key, _TRIAL_VALUE, 0, winreg.REG_SZ, str(start))
    except (ImportError, OSError):
        pass


def _trial_start(folder: Path, now: float, use_registry: bool = False) -> float:
    """The earliest recorded start wins, so deleting trial.txt does not restart the trial."""
    folder.mkdir(parents=True, exist_ok=True)
    stamp = folder / "trial.txt"
    in_file: float | None = None
    if stamp.exists():
        try:
            in_file = float(stamp.read_text(encoding="utf-8").strip())
        except ValueError:
            in_file = None
    in_registry = _registry_trial() if use_registry else None
    known = [value for value in (in_file, in_registry) if value is not None]
    start = min(known) if known else now
    if in_file != start:
        stamp.write_text(str(start), encoding="utf-8")
    if use_registry and in_registry != start:
        _save_registry_trial(start)
    return start


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)
