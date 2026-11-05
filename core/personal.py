"""What the user tells ORION about themselves and how they want him to behave.

"My name is Nick" / "call me Nick"          -> the name he addresses them by
"I live in London" / "my city is London"    -> the default city (weather)
"say sir at the end of everything you say"  -> a reply ending added to every reply
"from now on, keep answers short"           -> a standing instruction given to the model every turn

These are saved where they take effect (preferences or instruction memories), not only
remembered as loose facts. In real use "My name is Nick" was stored as a memory while he
kept calling the user "Sir", and "say sir after everything" was simply repeated back.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_POLITE = re.compile(
    r"^(?:(?:hey|ok|okay|hi)\s+)?(?:orion[,\s]+)?(?:please\s+|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|would\s+you\s+(?:please\s+)?|will\s+you\s+|i\s+want\s+you\s+to\s+|i(?:'d| would)\s+like\s+you\s+to\s+|i\s+need\s+you\s+to\s+|go\s+ahead\s+and\s+|just\s+)*",
    re.IGNORECASE,
)
_TRAILING = re.compile(r"(?:[\s,]+(?:please|for me|orion|thanks|thank you|now|right now))+([?.!]*)$", re.IGNORECASE)
_OPEN_MY = re.compile(r"^(open|launch|start|close|quit)\s+(?:up\s+)?(?:my|the)\s+", re.IGNORECASE)

_NAME = re.compile(
    r"^(?:(?:hi|hello|hey)[,\s]+)?(?:my (?:nick)?name is|my (?:nick)?name's|i am called|i'm called|call me|you can call me|please call me|just call me|i go by)\s+(?P<name>[A-Za-z][A-Za-z' -]{0,30}?)[.!]?$",
    re.IGNORECASE,
)
_CITY = re.compile(
    r"^(?:i live in|i'm in|i am in|i'm based in|i am based in|my city is|my home city is|my default city is|set my city to|i'm from|i am from)\s+(?P<city>[A-Za-z][A-Za-z .,'-]{1,48}?)[.!]?$",
    re.IGNORECASE,
)
_SUFFIX = re.compile(
    r"(?:from now on[,\s]+|always\s+|please\s+)*(?:say|add|put|call me|end (?:every|each|all)(?: of)? (?:your )?(?:sentences?|replies|answers|messages?) with|finish (?:every|each) (?:reply|answer|sentence) with)\s+[\"'“]?(?P<word>[A-Za-z][A-Za-z ,.!']{0,24}?)[\"'”]?\s*(?:at the end of|after|to the end of|on the end of)?\s*(?:everything|every(?:thing)? (?:you say|reply|answer|sentence|message)|each (?:reply|answer|sentence|message)|all (?:your )?(?:replies|answers|sentences))?(?:\s+you (?:say|make|write|give))?[.!]?$",
    re.IGNORECASE,
)
_STOP_SUFFIX = re.compile(r"\b(?:stop|don't|do not|no more)\s+(?:saying|adding|ending with)\s+[\"'“]?(?P<word>[A-Za-z ]{1,24}?)[\"'”]?(?:\s+at the end.*)?[.!]?$", re.IGNORECASE)
_INSTRUCTION = re.compile(
    r"^(?:from now on|going forward|always|never|whenever i|every time i|in future|in the future)\b[,\s]*(?P<rule>.{4,200}?)[.!]?$",
    re.IGNORECASE,
)
_FORGET_RULES = re.compile(r"^(?:forget|clear|drop|remove)\s+(?:all\s+)?(?:my\s+|your\s+)?(?:standing\s+)?(?:instructions|rules)\b", re.IGNORECASE)
_NOT_A_NAME = {"a", "an", "the", "not", "just", "here", "busy", "tired", "fine", "good", "ok", "okay", "back", "home", "ready", "sorry", "going"}


def plain(text: str) -> str:
    """A request without the politeness around it, so fast paths match how people really talk.

    "I want you to open my calculator." -> "open calculator."
    """
    cleaned = " ".join(text.strip().split())
    cleaned = _POLITE.sub("", cleaned)
    cleaned = _TRAILING.sub(lambda match: match.group(1), cleaned)
    cleaned = _OPEN_MY.sub(lambda match: f"{match.group(1)} ", cleaned)
    return cleaned[:1].lower() + cleaned[1:] if cleaned[:1].isupper() and not cleaned[:2].isupper() else cleaned


@dataclass(frozen=True)
class Personal:
    kind: str  # name | city | suffix | stop_suffix | instruction | forget_instructions
    value: str


def personal_statement(text: str) -> Personal | None:
    body = " ".join(text.strip().split())
    if not body or len(body) > 220:
        return None
    match = _NAME.match(body)
    if match:
        name = match.group("name").strip(" '-")
        if name.split()[0].lower() not in _NOT_A_NAME and len(name.split()) <= 3:
            return Personal("name", " ".join(part[:1].upper() + part[1:] for part in name.split()))
    match = _CITY.match(body)
    if match:
        # "Lisbon, Portugal" -> Lisbon: the weather service wants the city itself.
        city = match.group("city").split(",")[0].strip(" .'-")
        if city.lower() not in _NOT_A_NAME:
            return Personal("city", city.title())
    match = _STOP_SUFFIX.search(body)
    if match:
        return Personal("stop_suffix", match.group("word").strip())
    if re.search(r"\b(?:at the end of|after|end (?:every|each|all)|finish (?:every|each))\b", body, re.IGNORECASE):
        match = _SUFFIX.search(body)
        if match:
            word = match.group("word").strip(" ,.!")
            if 0 < len(word.split()) <= 4:
                return Personal("suffix", word)
    if _FORGET_RULES.match(body):
        return Personal("forget_instructions", "")
    match = _INSTRUCTION.match(body)
    if match:
        return Personal("instruction", body.rstrip(".!") + ".")
    return None


def with_suffix(reply: str, suffix: str | None) -> str:
    """'It's four fourteen.' + 'sir' -> 'It's four fourteen, sir.'"""
    if not suffix or not reply.strip():
        return reply
    text = reply.rstrip()
    if re.search(rf"\b{re.escape(suffix)}[.!?]*$", text, re.IGNORECASE):
        return reply
    end = text[-1] if text[-1] in ".!?" else "."
    body = text[:-1] if text[-1] in ".!?" else text
    return f"{body.rstrip(',')}, {suffix}{end}"


_CLAUSES = re.compile(r"\s*(?:,\s*(?:and|but|also)\s+|;\s*|\.\s+(?=[A-Z])|\s+and\s+(?=(?:call|say|my|i\s|i'm|always|never|from now on)\b))", re.IGNORECASE)


def personal_statements(text: str) -> list[Personal]:
    """Every setting in one message: "My nickname is Sam, and call me Sir at the end of every sentence"."""
    whole = personal_statement(text)
    found = []
    for clause in _CLAUSES.split(" ".join(text.strip().split())):
        item = personal_statement(clause)
        if item is not None and item not in found:
            found.append(item)
    if len(found) > 1:
        return found
    if whole is not None:
        return [whole]
    return found
