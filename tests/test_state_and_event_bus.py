from __future__ import annotations

from core.state import AppState


def test_busy_states() -> None:
    assert AppState.IDLE.busy is False
    assert AppState.THINKING.busy is True
    assert AppState.ERROR.busy is False


def test_tools_are_offered_only_for_tasks() -> None:
    from core.intent_router import offer_tools

    assert offer_tools("hello") is False
    assert offer_tools("hello jar") is False
    assert offer_tools("can you speak?") is False
    assert offer_tools("you're not") is False
    assert offer_tools("what time is it") is True
    assert offer_tools("how much battery do I have") is True
