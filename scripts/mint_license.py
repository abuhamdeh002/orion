"""Issue a license key with the private key in cloud/site/.dev.vars (for your own PCs, or testing).

    python scripts/mint_license.py                    # lifetime + cloud, written to ORION's data folder
    python scripts/mint_license.py --plan lifetime    # no cloud relay
    python scripts/mint_license.py --days 30 --print  # 30-day key, printed instead of installed

The private key never leaves this machine. Never commit .dev.vars or paste the key anywhere.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.license import sign_license, verify_license  # noqa: E402
from app.paths import app_data_dir  # noqa: E402


def private_key() -> bytes:
    for line in (ROOT / "cloud" / "site" / ".dev.vars").read_text(encoding="utf-8").splitlines():
        if line.startswith("LICENSE_PRIVATE_HEX="):
            return bytes.fromhex(line.split("=", 1)[1].strip())
    raise SystemExit("LICENSE_PRIVATE_HEX is not in cloud/site/.dev.vars.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan", choices=["lifetime", "cloud", "bundle"], default="bundle")
    parser.add_argument("--days", type=int, default=0, help="0 means no expiry")
    parser.add_argument("--print", dest="show", action="store_true", help="print the key instead of installing it")
    args = parser.parse_args()
    payload = {"plan": args.plan, "cloud": args.plan != "lifetime", "sub": "owner"}
    if args.days:
        payload["exp"] = int(time.time()) + args.days * 86400
    key = sign_license(payload, private_key())
    state = verify_license(key)
    if state.plan == "expired":
        raise SystemExit("The key did not verify against app/license.py. Is .dev.vars from the same rotation?")
    if args.show:
        print(key)
        return
    target = app_data_dir() / "license.key"
    target.write_text(key, encoding="utf-8")
    print(f"Installed a {state.plan} license (cloud={state.cloud}) at {target}. Restart ORION.")


if __name__ == "__main__":
    main()
