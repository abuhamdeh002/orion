"""ORION entry point. Same as `python -m service`: starts the always-on service and opens its window."""

from __future__ import annotations

import sys

from service.__main__ import main

if __name__ == "__main__":
    if "--background" not in sys.argv:
        sys.argv.append("--open")
    main()
