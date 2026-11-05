"""Explicit allowlist of tools the assistant may invoke."""

from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[BaseTool]:
        return [self._tools[name] for name in self.names()]

    def openai_tool_schemas(self) -> list[dict[str, Any]]:
        """Generate OpenAI-compatible function-calling tool definitions.

        Each registered tool's input_schema (a Pydantic model) is converted to
        a JSON Schema and wrapped in the OpenAI tool format.
        """
        schemas: list[dict[str, Any]] = []
        for tool in self.all():
            json_schema = _simplify_schema(tool.input_schema.model_json_schema())
            json_schema.pop("title", None)
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": json_schema,
                    },
                }
            )
        return schemas


def _simplify_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Drop JSON Schema forms Ollama's parser rejects, mainly anyOf null unions."""
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key in {"title", "$defs", "definitions"}:
            continue
        if isinstance(value, dict):
            cleaned[key] = _simplify_schema(value)
        elif isinstance(value, list):
            cleaned[key] = [_simplify_schema(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    union = cleaned.get("anyOf")
    if isinstance(union, list):
        non_null = [item for item in union if item.get("type") != "null"]
        if len(non_null) == 1:
            flattened = dict(non_null[0])
            for key, value in cleaned.items():
                if key not in flattened and key not in {"anyOf", "default"}:
                    flattened[key] = value
            return flattened
    if cleaned.get("default") is None:
        cleaned.pop("default", None)
    return cleaned


DEFAULT_WINDOWS_APPS: list[tuple[str, str]] = [
    ("notepad", r"C:\Windows\System32\notepad.exe"),
    ("calc", r"C:\Windows\System32\calc.exe"),
    ("mspaint", r"C:\Windows\System32\mspaint.exe"),
    ("explorer", r"C:\Windows\explorer.exe"),
]


def create_default_registry(
    config: Any = None,
    reminder_repository: Any = None,
    memory_repository: Any = None,
    background: Any = None,
) -> ToolRegistry:
    """Create and populate a ToolRegistry with the built-in tools."""
    from tools.application_tool import ApplicationTool
    from tools.browser_tool import BrowserTool
    from tools.system_info_tool import SystemInfoTool
    from tools.time_tool import TimeDateTool

    registry = ToolRegistry()
    registry.register(TimeDateTool())
    search_url = getattr(config, "search_url_template", "https://duckduckgo.com/?q={query}")
    registry.register(BrowserTool(search_url_template=search_url))
    configured = list(getattr(config, "allowed_apps", []) or [])
    launcher = ApplicationTool(allowed_apps=[*DEFAULT_WINDOWS_APPS, *configured])
    registry.register(launcher)
    registry.register(SystemInfoTool())
    from tools.app_control import AppControlTool
    from tools.computer_tool import ComputerTool, PowerTool

    registry.register(AppControlTool())
    registry.register(ComputerTool())
    registry.register(PowerTool())
    from tools.routine_tool import RoutineTool

    registry.register(RoutineTool())
    if background is not None:
        from tools.watch_tool import WatchTool

        registry.register(WatchTool(background))
    if config is not None:
        from tools.messaging_tool import MessagingTool
        from tools.music_tool import MusicTool
        from tools.vision_tool import VisionTool
        from tools.weather_tool import WeatherTool

        registry.register(WeatherTool(config))
        registry.register(MusicTool(config, launcher=launcher))
        registry.register(VisionTool(config))
        registry.register(MessagingTool(config))
    if reminder_repository is not None:
        from tools.reminder_tool import ReminderTool

        registry.register(ReminderTool(reminder_repository))
    if memory_repository is not None:
        from tools.memory_tool import MemoryTool

        registry.register(MemoryTool(memory_repository))
    return registry
