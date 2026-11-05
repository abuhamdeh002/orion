from __future__ import annotations

from core.conversation_manager import ConversationManager


def test_context_includes_system_prompt_and_truncates() -> None:
    manager = ConversationManager(max_messages=3, system_prompt="You are Orion.")
    for index in range(6):
        manager.add("user", f"msg {index}")
        manager.add("assistant", f"reply {index}")
    window = manager.context_window()
    assert window[0].role == "system"
    assert window[0].content == "You are Orion."
    assert len(window) == 4  # system + last 3
    assert window[-1].content == "reply 5"


def test_tool_payload_includes_ids_and_is_not_split() -> None:
    manager = ConversationManager(max_messages=2, system_prompt="sys")
    manager.add("user", "old")
    manager.add(
        "assistant",
        "",
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "time_date", "arguments": "{}"},
            }
        ],
    )
    manager.add("tool", '{"ok": true}', tool_name="time_date", tool_call_id="call_1")
    manager.add("assistant", "It is noon.")
    payload = manager.provider_payload()
    roles = [item["role"] for item in payload]
    assert roles[0] == "system"
    assert "tool" in roles
    assistant = next(item for item in payload if item.get("tool_calls"))
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["content"] is None
    tool = next(item for item in payload if item["role"] == "tool")
    assert tool["tool_call_id"] == "call_1"
    assert payload.index(assistant) < payload.index(tool)


def test_clear_history() -> None:
    manager = ConversationManager(system_prompt="sys")
    manager.add("user", "hello")
    manager.clear()
    assert manager.history() == []
    payload = manager.provider_payload()
    assert payload == [{"role": "system", "content": "sys"}]
