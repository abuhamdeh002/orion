from __future__ import annotations

from app.config import AppConfig
from app.errors import ProviderConfigurationError, ProviderError
from core.assistant import Assistant
from core.state import AppState
from tests.conftest import FakeProvider


def test_typed_conversation_with_fake_provider(app_config: AppConfig) -> None:
    provider = FakeProvider("Hello, sir.")
    assistant = Assistant(app_config, provider)
    reply = assistant.handle_user_message("Tell me about the files.")
    assert reply.error is False
    assert reply.text == "Hello, sir."
    assert len(provider.calls) == 1
    roles = [item["role"] for item in provider.calls[0]]
    assert roles[0] == "system"
    assert roles[-1] == "user"


def test_empty_message_is_rejected(app_config: AppConfig) -> None:
    assistant = Assistant(app_config, FakeProvider())
    reply = assistant.handle_user_message("   ")
    assert reply.error is True


def test_missing_api_key_error_is_user_facing(app_config: AppConfig) -> None:
    provider = FakeProvider(fail=ProviderConfigurationError("OPENAI_API_KEY is not configured"))
    assistant = Assistant(app_config, provider)
    reply = assistant.handle_user_message("Tell me about the files.")
    assert reply.error is True
    assert "OPENAI_API_KEY" in reply.text
    assert reply.state == AppState.ERROR


def test_provider_error_does_not_crash(app_config: AppConfig) -> None:
    provider = FakeProvider(fail=ProviderError("rate limited"))
    assistant = Assistant(app_config, provider)
    reply = assistant.handle_user_message("Tell me about the files.")
    assert reply.error is True
    assert "rate limited" in reply.text


def test_cancel_during_provider_call(app_config: AppConfig) -> None:
    assistant_box: dict[str, Assistant] = {}
    provider = FakeProvider(text="should not be shown", on_chat=lambda: assistant_box["a"].cancel())
    assistant = Assistant(app_config, provider)
    assistant_box["a"] = assistant
    reply = assistant.handle_user_message("Tell me about the files.")
    assert reply.error is True
    assert reply.text == "Cancelled."


def test_multi_turn_keeps_prior_user_messages(app_config: AppConfig) -> None:
    provider = FakeProvider("ok")
    assistant = Assistant(app_config, provider)
    assistant.handle_user_message("first")
    assistant.handle_user_message("second")
    last_payload = provider.calls[-1]
    user_contents = [item["content"] for item in last_payload if item["role"] == "user"]
    assert "first" in user_contents
    assert "second" in user_contents


def test_assistant_executes_tool_call(app_config: AppConfig) -> None:
    from ai.base_provider import ChatResponse, ToolCallRequest
    from tools.registry import create_default_registry

    tools = create_default_registry(app_config)
    round1 = ChatResponse(
        text="",
        model="fake",
        tool_calls=[
            ToolCallRequest(
                id="call_1",
                name="time_date",
                arguments={"query": "time"},
            )
        ],
    )
    round2 = ChatResponse(
        text="The current time was retrieved.",
        model="fake",
    )
    provider = FakeProvider(responses=[round1, round2])
    assistant = Assistant(app_config, provider, tools=tools)

    reply = assistant.handle_user_message("Look up the current time for me please")
    assert reply.error is False
    assert reply.text == "The current time was retrieved."
    assert reply.tool_results is not None
    assert len(reply.tool_results) == 1
    assert reply.tool_results[0]["tool"] == "time_date"
    assert reply.tool_results[0]["ok"] is True
    assert len(provider.calls) == 2


def test_confirmation_is_denied_without_a_callback(app_config: AppConfig) -> None:
    from ai.base_provider import ChatResponse, ToolCallRequest
    from pydantic import BaseModel
    from tools.base_tool import BaseTool, ToolResult
    from tools.registry import ToolRegistry
    from core.permissions import RiskLevel

    class Args(BaseModel):
        name: str = "x"

    class Risky(BaseTool):
        name = "risky"
        description = "Does something consequential"
        risk = RiskLevel.HIGH
        requires_confirmation = True

        @property
        def input_schema(self) -> type[BaseModel]:
            return Args

        def execute(self, arguments: BaseModel) -> ToolResult:
            return ToolResult(ok=True, message="ran")

    registry = ToolRegistry()
    registry.register(Risky())
    round1 = ChatResponse(
        text="",
        model="fake",
        tool_calls=[ToolCallRequest(id="c1", name="risky", arguments={"name": "x"})],
    )
    round2 = ChatResponse(text="I did not run it.", model="fake")
    provider = FakeProvider(responses=[round1, round2])
    assistant = Assistant(app_config, provider, tools=registry)
    reply = assistant.handle_user_message("do the risky thing")
    assert reply.tool_results is not None
    assert reply.tool_results[0]["ok"] is False
    assert "not confirmed" in reply.tool_results[0]["message"]


def test_confirmation_callback_can_approve(app_config: AppConfig) -> None:
    from ai.base_provider import ChatResponse, ToolCallRequest
    from pydantic import BaseModel
    from tools.base_tool import BaseTool, ToolResult
    from tools.registry import ToolRegistry
    from core.permissions import RiskLevel

    class Args(BaseModel):
        name: str = "x"

    class Risky(BaseTool):
        name = "risky"
        description = "Does something consequential"
        risk = RiskLevel.HIGH
        requires_confirmation = True

        @property
        def input_schema(self) -> type[BaseModel]:
            return Args

        def execute(self, arguments: BaseModel) -> ToolResult:
            return ToolResult(ok=True, message="ran")

    registry = ToolRegistry()
    registry.register(Risky())
    round1 = ChatResponse(
        text="",
        model="fake",
        tool_calls=[ToolCallRequest(id="c1", name="risky", arguments={"name": "x"})],
    )
    round2 = ChatResponse(text="Done.", model="fake")
    provider = FakeProvider(responses=[round1, round2])
    seen: list[str] = []
    assistant = Assistant(
        app_config,
        provider,
        tools=registry,
        confirm=lambda request: seen.append(request.tool_name) or True,
    )
    reply = assistant.handle_user_message("do the risky thing")
    assert seen == ["risky"]
    assert reply.tool_results is not None
    assert reply.tool_results[0]["ok"] is True


def test_assistant_handles_unknown_tool(app_config: AppConfig) -> None:
    from ai.base_provider import ChatResponse, ToolCallRequest

    round1 = ChatResponse(
        text="",
        model="fake",
        tool_calls=[
            ToolCallRequest(
                id="call_unknown",
                name="nonexistent_tool",
                arguments={},
            )
        ],
    )
    round2 = ChatResponse(
        text="I could not execute that tool.",
        model="fake",
    )
    provider = FakeProvider(responses=[round1, round2])
    assistant = Assistant(app_config, provider)

    reply = assistant.handle_user_message("Do something impossible")
    assert reply.error is False
    assert reply.tool_results is not None
    assert reply.tool_results[0]["ok"] is False
    assert "not available" in reply.tool_results[0]["message"]

