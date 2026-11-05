"""Instant commands. These never go through the model."""

from __future__ import annotations

import re

_YES = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|do it|send it|go ahead|confirm|please do)[!.\s]*$",
    re.IGNORECASE,
)
_NO = re.compile(
    r"^(?:no|nope|nah|cancel|stop|don't|do not|never mind)[!.\s]*$",
    re.IGNORECASE,
)
_OPEN = re.compile(r"^(?:please\s+)?(?:open|launch|start)\s+(.+?)[!.\s]*$", re.IGNORECASE)
_PLAY = re.compile(
    r"^(?:please\s+)?(?:play|put on)\s+(.+?)(?:\s+on\s+spotify)?[!.\s]*$",
    re.IGNORECASE,
)
_MEDIA = re.compile(
    r"^(?:please\s+)?(?:pause(?:\s+the\s+music|\s+spotify)?|next(?:\s+song)?|skip|previous(?:\s+song)?|last song)[!.\s]*$",
    re.IGNORECASE,
)
_DISCORD = re.compile(
    r"^(?:please\s+)?(?:message|text|dm)\s+(.+?)\s+on\s+discord\s+(?:saying|that|:)\s+(.+?)[!.\s]*$",
    re.IGNORECASE,
)
_DISCORD_OPEN = re.compile(
    r"^(?:please\s+)?(?:open|jump to)\s+(.+?)\s+(?:on|in)\s+discord[!.\s]*$",
    re.IGNORECASE,
)
_SEARCH = re.compile(
    r"^(?:please\s+)?(?:search|look up|find)\s+(.+?)\s+in\s+([a-z][a-z0-9 .+-]{1,40})[!.\s]*$",
    re.IGNORECASE,
)


def is_yes(text: str) -> bool:
    return bool(_YES.match(" ".join(text.strip().split())))


def is_no(text: str) -> bool:
    return bool(_NO.match(" ".join(text.strip().split())))


def parse_command(text: str) -> dict[str, str] | None:
    cleaned = " ".join(text.strip().split())
    if not cleaned or cleaned.endswith("?"):
        return None
    match = _DISCORD.match(cleaned)
    if match:
        return {"action": "discord_message", "target": match.group(1).strip(), "text": match.group(2).strip()}
    match = _DISCORD_OPEN.match(cleaned)
    if match:
        return {"action": "discord_open", "target": match.group(1).strip()}
    match = _SEARCH.match(cleaned)
    if match:
        return {"action": "search", "query": match.group(1).strip(), "name": match.group(2).strip()}
    match = _MEDIA.match(cleaned)
    if match:
        word = cleaned.lower()
        if word.startswith("next") or word.startswith("skip"):
            control = "next"
        elif "previous" in word or "last" in word:
            control = "previous"
        else:
            control = "pause"
        return {"action": "media", "name": control}
    match = _PLAY.match(cleaned)
    if match:
        query = re.sub(r"\s+on\s+spotify$", "", match.group(1).strip(), flags=re.IGNORECASE)
        if query:
            return {"action": "play", "query": query}
    match = _OPEN.match(cleaned)
    if match:
        name = re.sub(r"\s+again$", "", match.group(1).strip(), flags=re.IGNORECASE)
        if name and name.lower() not in {"it", "that", "the", "again", "this", "them"}:
            return {"action": "open", "name": name}
    return None


def confirmation_line(arguments: dict[str, str]) -> str:
    action = arguments.get("action")
    if action == "discord_message":
        return f"Send \"{arguments.get('text', '')}\" to {arguments.get('target', 'them')} on Discord?"
    if action == "whatsapp":
        return f"Send \"{arguments.get('text', '')}\" on WhatsApp?"
    if action == "open":
        return f"Open {arguments.get('name', 'that app')}?"
    return "Shall I go ahead?"
