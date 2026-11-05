"""Each entry point owns its turn: confirmations, pending actions, and history budget."""

from __future__ import annotations

import threading
import time

from pydantic import BaseModel

from ai.base_provider import ChatResponse, ToolCallRequest
from core.assistant import Assistant, _fit_budget
from core.permissions import RiskLevel
from tests.conftest import FakeProvider
from tools.base_tool import BaseTool, ToolResult
from tools.registry import ToolRegistry


class _Args(BaseModel):
    target: str = "x"


class _Lock(BaseTool):
    name = "computer"
    description = "Lock the PC"
    risk = RiskLevel.MEDIUM

    def __init__(self) -> None:
        self.runs = 0

    @property
    def input_schema(self) -> type[BaseModel]:
        return _Args

    def needs_confirmation_for(self, arguments: dict) -> bool:
        return True

    def execute(self, arguments: BaseModel) -> ToolResult:
        self.runs += 1
        return ToolResult(ok=True, message="Locked.")


def _assistant(app_config, responses):
    tool = _Lock()
    registry = ToolRegistry()
    registry.register(tool)
    return Assistant(app_config, FakeProvider(responses=responses), tools=registry), tool


def _lock_call():
    return ChatResponse(text="", model="fake", tool_calls=[ToolCallRequest(id="c1", name="computer", arguments={"target": "pc"})])


def test_remote_sources_are_asked_in_the_reply_and_act_on_yes(app_config) -> None:
    assistant, tool = _assistant(app_config, [_lock_call()])
    reply = assistant.handle_user_message("lock the pc", source="web", ask_on_reply=True)
    assert reply.needs_confirm is True
    assert tool.runs == 0
    done = assistant.handle_user_message("yes", source="web", ask_on_reply=True)
    assert tool.runs == 1
    assert done.text == "Locked."


def test_a_yes_from_another_source_does_not_approve(app_config) -> None:
    assistant, tool = _assistant(app_config, [_lock_call(), ChatResponse(text="Hello.", model="fake")])
    assistant.handle_user_message("lock the pc", source="web", ask_on_reply=True)
    assistant.handle_user_message("yes", source="telegram", ask_on_reply=True)
    assert tool.runs == 0
    assert assistant.has_pending("web")


def test_no_cancels_and_history_stays_valid(app_config) -> None:
    assistant, tool = _assistant(app_config, [_lock_call()])
    assistant.handle_user_message("lock the pc", source="web", ask_on_reply=True)
    assert assistant.handle_user_message("no", source="web", ask_on_reply=True).text == "Cancelled."
    assert tool.runs == 0
    roles = [message.role for message in assistant.history()]
    # The model's tool call is closed by a tool message, so strict providers accept the history.
    assert roles[roles.index("assistant") + 1] == "tool"


def test_voice_confirm_callback_is_per_turn(app_config) -> None:
    assistant, tool = _assistant(app_config, [_lock_call(), ChatResponse(text="Done.", model="fake")])
    asked = []
    assistant.handle_user_message("lock the pc", source="voice", confirm=lambda request: asked.append(request.tool_name) or True)
    assert asked == ["computer"] and tool.runs == 1
    assert assistant.confirm is None


def test_a_second_request_waits_instead_of_cancelling(app_config) -> None:
    class Slow(FakeProvider):
        def chat(self, messages, tools=None):
            time.sleep(0.3)
            return ChatResponse(text="first done", model="fake")

    assistant = Assistant(app_config, Slow(), tools=ToolRegistry())
    results = {}
    worker = threading.Thread(target=lambda: results.setdefault("a", assistant.handle_user_message("first long question", source="voice")))
    worker.start()
    time.sleep(0.05)
    results["b"] = assistant.handle_user_message("second question", source="telegram")
    worker.join()
    assert results["a"].text == "first done"
    assert results["b"].text == "first done"


def test_budget_keeps_current_turn_and_never_orphans_tool_results() -> None:
    history = [{"role": "system", "content": "s"}]
    history += [{"role": "user", "content": "x" * 3000}, {"role": "assistant", "content": "", "tool_calls": [{}]}]
    history += [{"role": "tool", "content": "y" * 5000}, {"role": "assistant", "content": "ok"}]
    history += [{"role": "user", "content": "and tomorrow?"}]
    fitted = _fit_budget(history, 2_000)
    assert fitted[0]["role"] == "system"
    assert fitted[-1]["content"] == "and tomorrow?"
    non_system = [item for item in fitted if item["role"] != "system"]
    assert non_system[0]["role"] != "tool"
