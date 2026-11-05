from ai.ollama_provider import _ollama_messages


def test_ollama_tool_arguments_are_objects() -> None:
    messages = _ollama_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "time_date", "arguments": '{"query": "time"}'},
                    }
                ],
            },
            {"role": "tool", "content": '{"ok": true}', "name": "time_date", "tool_call_id": "call_1"},
        ]
    )
    assert messages[0]["content"] == ""
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == {"query": "time"}
    assert messages[1]["tool_name"] == "time_date"
