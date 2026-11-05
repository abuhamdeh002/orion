"""Pick out personal facts the user states in passing, so they can be recalled later.

Deliberately cheap and conservative: a handful of first-person patterns, no
model call. Every captured fact is saved with kind="auto" and shows up on the
Memory page, where it can be deleted.
"""

from __future__ import annotations

import re

_RELATIONS = (
    "wife|husband|partner|girlfriend|boyfriend|sister|brother|mum|mom|mother|dad|father|son|daughter|"
    "boss|manager|friend|best friend|dog|cat|kid|kids|children"
)

_PATTERNS = (
    re.compile(r"\bmy name is ([a-z][\w' -]{1,40})", re.IGNORECASE),
    re.compile(r"\bcall me ([a-z][\w' -]{1,30})", re.IGNORECASE),
    re.compile(rf"\bmy (?:{_RELATIONS})(?:'s name)? is (?:called |named )?[a-z][\w' -]{{1,40}}", re.IGNORECASE),
    re.compile(r"\bi (?:really )?(?:like|love|prefer|hate|can't stand|am allergic to) [\w' ,-]{2,60}", re.IGNORECASE),
    re.compile(r"\bi(?: am|'m) (?:a|an) [\w' -]{2,40}", re.IGNORECASE),
    re.compile(r"\bi live in [\w' ,-]{2,40}", re.IGNORECASE),
    re.compile(r"\bi work (?:at|for|as) [\w' ,&-]{2,40}", re.IGNORECASE),
    re.compile(r"\bmy birthday is [\w' ,-]{2,30}", re.IGNORECASE),
)

_SKIP = re.compile(r"\?\s*$|\b(?:remember|remind|forget)\b", re.IGNORECASE)


def facts_in(text: str) -> list[str]:
    """Statements worth keeping, trimmed to the clause that holds the fact."""
    cleaned = " ".join(text.strip().split())
    if not cleaned or _SKIP.search(cleaned) or len(cleaned) > 300:
        return []
    found: list[str] = []
    for clause in re.split(r"(?<=[.!;])\s+|,\s+(?:and|but)\s+", cleaned):
        for pattern in _PATTERNS:
            match = pattern.search(clause)
            if match:
                fact = clause[match.start():].strip(" .!;,")
                fact = fact[0].upper() + fact[1:]
                if fact not in found:
                    found.append(fact)
                break
    return found


def capture(memory, text: str) -> list[str]:
    """Save new facts from one user message. Returns what was saved."""
    if memory is None:
        return []
    saved = []
    for fact in facts_in(text):
        existing = {item["text"].lower() for item in memory.recall(fact, limit=5)}
        if fact.lower() in existing:
            continue
        memory.remember(fact, kind="auto")
        saved.append(fact)
    return saved
