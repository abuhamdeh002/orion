"""Real actions. If this module did not do it, it did not happen."""

from __future__ import annotations

import ast
import re
from pathlib import Path

_last_folder: Path | None = None
# These run before the model and some have side effects (opening Outlook, creating folders),
# so each needs the whole request to be about it, not one word somewhere in the sentence.
_CONNECT = re.compile(
    r"\b(?:connect|link|add|hook up|set\s*up|setup)\b.*\b(?:calendar|outlook|google calendar)\b",
    re.IGNORECASE,
)
_AGENDA = re.compile(
    r"^(?:please\s+)?(?:(?:what(?:'s| is)|what do i have)\s+(?:on\s+)?(?:my|the)\s+|(?:show|open|check|read)\s+(?:me\s+)?(?:my\s+)?|"
    r"do i have (?:any\s+)?|any\s+|my\s+)?(?:calendar|meetings?|agenda|appointments?|schedule)\b"
    r"(?:\s+(?:today|tomorrow|for today|this week))?[?.!\s]*$",
    re.IGNORECASE,
)
# A question about meetings ("who are we meeting with?"), not a statement ("the meeting went well").
_AGENDA_QUESTION = re.compile(
    r"^(?:who|what|when|where|which|do|does|is|are|am|have|any)\b.*\b(?:calendar|meetings?|agenda|appointments?)\b",
    re.IGNORECASE,
)
_REOPEN = re.compile(
    r"^(?:please\s+)?(?:re-?open|open|show(?:\s+me)?|locate)\s+(?:it|that|the\s+(?:project|folder))(?:\s+again)?[!.\s]*$",
    re.IGNORECASE,
)
_MAKE = re.compile(
    r"^(?:please\s+)?(?:make|create)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:new\s+)?(?:project|folder|directory)\b",
    re.IGNORECASE,
)
_MATH = re.compile(r"(?<![\d-])(\d[\d,]*)(\s*)([*x×/+\-])(\s*)(\d[\d,]*)(?![\d-])", re.IGNORECASE)
_MATH_CUE = re.compile(r"^(?:what(?:'s| is)|calculate|compute|how much is|work out)\b", re.IGNORECASE)
# Claims of an action. Only checked when no tool ran this turn, so any of these is untrue.
_LIE = re.compile(
    r"\b(?:i(?:'ve| have)? (?:just )?(?:opened|created|made|launched|started|sent|set(?: up)?|scheduled|added|saved|paused|played|stopped|turned|muted|locked|closed)"
    r"|i'm (?:opening|creating|launching|setting|scheduling|playing|pausing)"
    r"|i(?:'ll| will) (?:remind|ping|alert|wake|nudge|beep|notify) you"
    r"|(?:reminder|timer|alarm)s? (?:is |has been |was )?(?:now )?(?:set|created|scheduled|added)"
    r"|(?:is|are) (?:now )?open(?: now)?\b|has (?:been )?opened|(?:is|are) now (?:playing|paused)"
    r"|application not found)\b",
    re.IGNORECASE,
)


def calendar_kind(text: str) -> str | None:
    cleaned = " ".join(text.strip().split())
    if re.search(r"\bremind", cleaned, re.IGNORECASE):
        return None
    if _CONNECT.search(cleaned):
        return "connect"
    if _AGENDA.match(cleaned) or _AGENDA_QUESTION.match(cleaned):
        return "read"
    return None


def wants_project(text: str) -> bool:
    return bool(_MAKE.search(text.strip()))


def wants_reopen(text: str) -> bool:
    return bool(_REOPEN.match(" ".join(text.strip().split())))


def spoken_math(text: str) -> str | None:
    cleaned = text.replace(",", "").strip()
    match = _MATH.search(cleaned)
    if match is None:
        return None
    spaced = bool(match.group(2)) and bool(match.group(4))
    # "555-1234" is a phone number and "1920x1080" a resolution, unless they asked for a sum.
    if not spaced and not _MATH_CUE.search(cleaned):
        return None
    op = {"x": "*", "×": "*"}.get(match.group(3).lower(), match.group(3))
    expression = f"{match.group(1)}{op}{match.group(5)}"
    try:
        value = _exact(expression)
    except (SyntaxError, ValueError, ZeroDivisionError):
        return None
    return f"That's {value}."


def make_project(text: str) -> str | None:
    if not _MAKE.search(text.strip()):
        return None
    named = re.search(r"\b(?:called|named|in)\s+([A-Za-z0-9][A-Za-z0-9 _-]{0,40})", text, re.IGNORECASE)
    raw = named.group(1) if named else "Project"
    name = re.sub(r"[^A-Za-z0-9 _-]", "", raw).strip() or "Project"
    folder = Path.home() / "Documents" / name
    folder.mkdir(parents=True, exist_ok=True)
    global _last_folder
    _last_folder = folder
    return f"Created {folder}."


def reopen_last(text: str) -> str | None:
    if not wants_reopen(text):
        return None
    if _last_folder is None or not _last_folder.exists():
        return "I have not created a project folder in this conversation."
    import os

    os.startfile(_last_folder)  # type: ignore[attr-defined]
    return f"Opened {_last_folder}."


def claims_unchecked_action(text: str, tool_results: list[dict] | None) -> bool:
    if tool_results:
        return False
    return bool(_LIE.search(text or ""))


def _exact(expression: str) -> int:
    tree = ast.parse(expression, mode="eval")
    return int(_eval(tree.body))


def _eval(node: ast.AST) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ZeroDivisionError
        if left % right:
            raise ValueError("not whole")
        return left // right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand)
    raise ValueError("unsupported")
