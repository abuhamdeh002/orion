"""Set while Orion is answering out loud, so the reply stays short."""

from __future__ import annotations

import contextvars

VOICE_TURN = contextvars.ContextVar("orion_voice_turn", default=False)

# Tool names the current sentence is about. The router narrows the tool list to these for the local model.
TOOL_FOCUS: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("orion_tool_focus", default=frozenset())
