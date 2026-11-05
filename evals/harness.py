"""Offline scores for routing decisions. This does not call a model."""

from __future__ import annotations

from core.intent_router import offer_tools

CASES = [
    ("hello", False),
    ("open notepad", True),
    ("what is on my clipboard", True),
    ("thanks", False),
    ("is today monday", False),
    ("I love this program", False),
    ("my display is broken", False),
    ("remind me at 5 to call mum", True),
]


def score_tool_choice() -> dict:
    hits = 0
    for text, expected in CASES:
        if offer_tools(text) is expected:
            hits += 1
    return {"cases": len(CASES), "correct": hits, "passed": hits == len(CASES)}


if __name__ == "__main__":
    print(score_tool_choice())
