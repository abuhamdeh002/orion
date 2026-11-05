"""Load skill manifests and report which ones really work right now.

Ready means the tools exist *and* whatever the skill needs is set up ("needs" names config
fields, e.g. a calendar link). The page used to call Calendar and Messaging ready with
nothing connected.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def load_skills(tools: list[str] | None = None, config: Any = None) -> list[dict]:
    available = set(tools or [])
    root = Path(__file__).resolve().parent
    skills = []
    for manifest in sorted(root.glob("*/skill.json")):
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        needed = payload.get("tools") or []
        missing = [name for name in needed if available and name not in available]
        for field, label in (payload.get("needs") or {}).items():
            if config is not None and not getattr(config, field, None):
                missing.append(label)
        if payload.get("probe") == "kdeconnect" and shutil.which("kdeconnect-cli") is None:
            missing.append("KDE Connect (kdeconnect-cli)")
        payload["ready"] = not missing
        payload["missing"] = missing
        payload.pop("needs", None)
        skills.append(payload)
    return skills
