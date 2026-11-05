"""Update KEY=value lines in the .env file without disturbing anything else in it."""

from __future__ import annotations

import os
import re
from pathlib import Path

_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_VALUE = re.compile(r"^[A-Za-z0-9_\-.:/+=]{0,256}$")


def set_env_values(path: Path, values: dict[str, str]) -> list[str]:
    """Write the given keys, keeping comments, order, and every other line. Returns the keys written."""
    for key, value in values.items():
        if not _KEY.match(key):
            raise ValueError(f"Not a valid setting name: {key}")
        if not _VALUE.match(value):
            raise ValueError(f"{key} contains characters a key never has.")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    updated: list[str] = []
    for line in lines:
        name = line.split("=", 1)[0].strip()
        if name in remaining and not line.lstrip().startswith("#"):
            updated.append(f"{name}={remaining.pop(name)}")
        else:
            updated.append(line)
    updated.extend(f"{key}={value}" for key, value in remaining.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    for key, value in values.items():
        # The running process may have these from the old file; the new values must win.
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    return list(values)
