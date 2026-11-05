"""Assistant runtime states used by both the engine and the UI."""

from __future__ import annotations

from enum import Enum


class AppState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"

    @property
    def label(self) -> str:
        return {
            AppState.IDLE: "Idle",
            AppState.LISTENING: "Listening",
            AppState.TRANSCRIBING: "Transcribing",
            AppState.THINKING: "Thinking",
            AppState.EXECUTING_TOOL: "Running tool",
            AppState.SPEAKING: "Speaking",
            AppState.ERROR: "Error",
        }[self]

    @property
    def busy(self) -> bool:
        return self in {
            AppState.LISTENING,
            AppState.TRANSCRIBING,
            AppState.THINKING,
            AppState.EXECUTING_TOOL,
            AppState.SPEAKING,
        }
