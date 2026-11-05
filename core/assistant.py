"""Central assistant service with tool execution loop. Qt-free so it can run on a worker thread."""

from __future__ import annotations

import json
import re
import logging
import threading
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from ai.base_provider import LLMProvider, ToolCallRequest
from ai.prompt_templates import build_system_prompt
from app.config import AppConfig
from app.errors import CancelledError, OrionError, ProviderConfigurationError, ProviderError
from core.context_manager import ContextManager
from core.conversation_manager import ChatMessage, ConversationManager
from core.intent_router import tools_for
from core.quick_reply import instant_reply
from core.voice_mode import TOOL_FOCUS, VOICE_TURN
from core.permissions import PermissionAction, PermissionGate, RiskLevel
from core.state import AppState
from tools.base_tool import BaseTool, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger("orion.assistant")

StateCallback = Callable[[AppState], None]

# Maximum number of tool-call round-trips before forcing a final text response
MAX_TOOL_ROUNDS = 5
CLOUD_TOOL_ROUNDS = 8


class AssistantReply(BaseModel):
    text: str
    state: AppState
    error: bool = False
    created_at: datetime
    tool_results: list[dict[str, Any]] | None = None
    needs_confirm: bool = False


class ConfirmationRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = {}
    reason: str
    summary: str


ConfirmCallback = Callable[[ConfirmationRequest], bool]


@dataclass(frozen=True)
class Turn:
    """Who is asking, and how to ask them back.

    Every entry point (voice, web, phone, Telegram) runs its own turn, so a "yes"
    typed on Telegram can never approve something asked on the web, and a phone
    request is never confirmed by whoever happens to be near the PC microphone.
    """

    source: str = "local"
    confirm: ConfirmCallback | None = None  # interactive: voice, a desktop dialog
    ask_on_reply: bool = False  # non-interactive: ask in the reply, act on the next "yes"
    preapproved: bool = False  # the person already said yes to exactly this action
    on_token: Callable[[str], None] | None = None  # live reply text, as it is generated


_TURN: ContextVar[Turn] = ContextVar("orion_turn", default=Turn())


class _AskUser(Exception):
    def __init__(self, request: ConfirmationRequest, call: ToolCallRequest) -> None:
        super().__init__(request.summary)
        self.request = request
        self.call = call


# Character budgets for the history sent with each request (about 4 characters per token).
_SHORT_BUDGET = 6_000
_LONG_BUDGET = 12_000
_TOOL_OUTPUT_LIMIT = 1_500


class Assistant:
    def __init__(
        self,
        config: AppConfig,
        provider: LLMProvider,
        conversation: ConversationManager | None = None,
        permissions: PermissionGate | None = None,
        tools: ToolRegistry | None = None,
        confirm: ConfirmCallback | None = None,
        conversation_repository: object | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.conversation = conversation or ConversationManager(
            max_messages=config.context_max_messages,
            system_prompt=build_system_prompt(config, self.tools.names()),
        )
        self.conversation.set_system_prompt(build_system_prompt(config, self.tools.names()))
        self.context = ContextManager(self.conversation, config)
        self.permissions = permissions or PermissionGate()
        self.confirm = confirm
        self.conversation_repository = conversation_repository
        self._cancel = threading.Event()
        self._epoch = 0
        self._turn_lock = threading.Lock()
        self.audit: Callable[[str, dict[str, Any]], None] | None = None
        self.pin_check: Callable[[], bool] | None = None
        self.on_token: Callable[[str], None] | None = None
        self.memory = None
        # Actions waiting for a "yes", one per source.
        self._pending: dict[str, dict[str, Any]] = {}
        # Tools used on the last turn, per source, so "and tomorrow?" keeps the weather tool.
        self._last_tools: dict[str, frozenset[str]] = {}
        # One turn at a time. A new request waits instead of cancelling the one in progress.
        self._run_lock = threading.Lock()
        if conversation_repository is not None and not self.conversation.history():
            conversation_repository.prune(config.history_retention_days)
            loaded = conversation_repository.load_recent(config.context_max_messages)
            if loaded:
                self.conversation.replace_history(loaded)

    def apply_config(
        self,
        config: AppConfig,
        provider: LLMProvider,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        if tools is not None:
            self.tools = tools
        self.conversation.max_messages = config.context_max_messages
        self.conversation.set_system_prompt(build_system_prompt(config, self.tools.names()))
        self.context.config = config

    def cancel(self) -> None:
        with self._turn_lock:
            self._epoch += 1
            self._cancel.set()
        abort = getattr(self.provider, "abort", None)
        if abort is not None:
            abort()

    def _begin_turn(self) -> int:
        with self._turn_lock:
            self._epoch += 1
            epoch = self._epoch
            self._cancel.clear()
            return epoch

    def _stale(self, epoch: int) -> bool:
        return epoch != self._epoch or self._cancel.is_set()

    def handle_user_message(
        self,
        text: str,
        on_state: StateCallback | None = None,
        *,
        source: str = "local",
        confirm: ConfirmCallback | None = None,
        ask_on_reply: bool = False,
        on_token: Callable[[str], None] | None = None,
    ) -> AssistantReply:
        turn = Turn(source=source, confirm=confirm, ask_on_reply=ask_on_reply, on_token=on_token)
        with self._run_lock:
            token = _TURN.set(turn)
            try:
                reply = self._handle(text, on_state)
            finally:
                _TURN.reset(token)
        suffix = getattr(self.config, "reply_suffix", None)
        if suffix and reply.text and not reply.needs_confirm:
            from core.personal import with_suffix

            reply.text = with_suffix(reply.text, suffix)
        return reply

    def _handle(self, text: str, on_state: StateCallback | None) -> AssistantReply:
        turn = _TURN.get()
        epoch = self._begin_turn()
        cleaned = text.strip()
        if not cleaned:
            return AssistantReply(
                text="Please enter a request.",
                state=AppState.IDLE,
                error=True,
                created_at=datetime.now(timezone.utc),
            )

        from core.command_parser import is_no, is_yes
        from core.reflex import clauses
        from tools.app_control import needs_confirmation

        pending = self._pending.pop(turn.source, None)
        if pending is not None:
            if is_yes(cleaned):
                self._remember("user", cleaned)
                return self._run_pending(pending, on_state)
            if is_no(cleaned):
                self._remember("user", cleaned)
                self._remember("assistant", "Cancelled.")
                self._set_state(on_state, AppState.IDLE)
                return AssistantReply(text="Cancelled.", state=AppState.IDLE, created_at=datetime.now(timezone.utc))
            # Anything else: the question lapses and this sentence is handled on its own.

        pieces = clauses(cleaned)
        if len(pieces) > 1 and all(self._is_reflex(piece) for piece in pieces):
            lines = [self._reflex_reply(piece, on_state) for piece in pieces]
            spoken = [item.text for item in lines if item is not None]
            return AssistantReply(
                text=" ".join(spoken),
                state=AppState.IDLE,
                error=any(item is not None and item.error for item in lines),
                created_at=datetime.now(timezone.utc),
            )

        reflex = self._reflex_reply(cleaned, on_state)
        if reflex is not None:
            return reflex

        if self._stale(epoch):
            raise CancelledError("Replaced by a newer request.")

        self._set_state(on_state, AppState.THINKING)
        memory_note = self._recall_memory(cleaned)
        self._remember("user", cleaned)
        self._capture_facts(cleaned)

        try:
            return self._run_conversation_loop(on_state, epoch, memory_note)
        except _AskUser as ask:
            self._pending[turn.source] = {"kind": "tool", "call": ask.call.model_dump()}
            line = _ask_line(ask.request)
            self._remember("assistant", line)
            self._set_state(on_state, AppState.IDLE)
            return AssistantReply(
                text=line,
                state=AppState.IDLE,
                created_at=datetime.now(timezone.utc),
                needs_confirm=True,
            )
        except CancelledError:
            logger.info("Assistant request cancelled")
            self._set_state(on_state, AppState.IDLE)
            return AssistantReply(
                text="Cancelled.",
                state=AppState.IDLE,
                error=True,
                created_at=datetime.now(timezone.utc),
            )
        except ProviderConfigurationError as exc:
            logger.warning("Provider configuration problem: %s", exc)
            return self._error_reply(str(exc), on_state)
        except ProviderError as exc:
            logger.warning("Provider error: %s", exc)
            return self._error_reply(str(exc), on_state)
        except OrionError as exc:
            logger.exception("Assistant error")
            return self._error_reply(str(exc), on_state)
        except Exception:
            logger.exception("Unexpected assistant failure")
            return self._error_reply(
                "Something went wrong while generating a reply. Check the log for details.",
                on_state,
            )

    def _run_conversation_loop(
        self,
        on_state: StateCallback | None,
        epoch: int,
        memory_note: str = "",
    ) -> AssistantReply:
        """Send messages to the LLM, execute tool calls, and loop until a final text response."""
        turn = _TURN.get()
        latest_user = next((message.content for message in reversed(self.conversation.history()) if message.role == "user"), "")
        wanted = tools_for(latest_user) & set(self.tools.names())
        if not wanted and len(latest_user.split()) <= 8:
            wanted = set(self._last_tools.get(turn.source, frozenset()))
        tool_schemas = self.tools.openai_tool_schemas() if wanted else None
        offered = sorted(wanted) if wanted else []
        budget = _SHORT_BUDGET if tool_schemas is None and len(latest_user.split()) < 16 else _LONG_BUDGET
        focus = TOOL_FOCUS.set(frozenset(wanted))
        try:
            reply = self._loop_rounds(on_state, epoch, tool_schemas, offered, budget, memory_note)
        finally:
            TOOL_FOCUS.reset(focus)
        used = frozenset(item["tool"] for item in reply.tool_results or [])
        self._last_tools[turn.source] = used
        return reply

    def _turn_messages(self, offered: list[str], budget: int, memory_note: str, correction: str = "") -> list[dict[str, Any]]:
        """The standing prompt never changes, so a local model keeps it cached.

        Everything that does change (time, name, standing instructions, memories, tools) is one
        note placed just before the latest user message.
        """
        from ai.prompt_templates import turn_note

        self.conversation.set_system_prompt(build_system_prompt(self.config))
        messages = _fit_budget(self.context.provider_messages(), budget)
        note = turn_note(
            self.config,
            offered,
            self.tools,
            instructions=self._instructions(),
            memories=memory_note,
            voice=VOICE_TURN.get(),
        )
        if correction:
            note = f"{note}\n{correction}"
        last_user = max((index for index, item in enumerate(messages) if item.get("role") == "user"), default=len(messages))
        return messages[:last_user] + [{"role": "system", "content": note}] + messages[last_user:]

    def _instructions(self) -> list[str]:
        if self.memory is None:
            return []
        try:
            return [item["text"] for item in self.memory.list_all() if item.get("kind") == "instruction"][:12]
        except Exception:
            logger.warning("Could not read standing instructions", exc_info=True)
            return []

    def _loop_rounds(
        self,
        on_state: StateCallback | None,
        epoch: int,
        tool_schemas: list[dict[str, Any]] | None,
        offered: list[str],
        budget: int,
        memory_note: str,
        correction: str = "",
    ) -> AssistantReply:
        all_tool_results: list[dict[str, Any]] = []

        round_num = 0
        limit = MAX_TOOL_ROUNDS
        retried = bool(correction)
        while round_num < limit:
            round_num += 1
            self._raise_if_cancelled()
            if self._stale(epoch):
                raise CancelledError("Replaced by a newer request.")
            self._set_state(on_state, AppState.THINKING)

            messages = self._turn_messages(offered, budget, memory_note, correction)
            sink = _TURN.get().on_token
            streamed = False
            if tool_schemas is None and sink is not None and not retried:
                response = self.provider.chat_stream(messages, self._guarded(sink))
                streamed = True
            else:
                response = self.provider.chat(messages, tools=tool_schemas)
            if getattr(self.provider, "last_backend", "local") != "local":
                limit = CLOUD_TOOL_ROUNDS
            self._raise_if_cancelled()

            # If the LLM didn't request any tool calls, we have a final response
            if not response.tool_calls:
                from core.hands import claims_unchecked_action

                if not retried and claims_unchecked_action(response.text or "", all_tool_results):
                    # It said "done" without doing anything. Offer the tools it needs and ask again.
                    retried = True
                    needed = (tools_for(response.text or "") | tools_for(_latest_user_text(self))) & set(self.tools.names())
                    offered = sorted(needed or set(self.tools.names()))
                    tool_schemas = self.tools.openai_tool_schemas()
                    correction = (
                        "You just said you did something, but you called no tool, so nothing happened. "
                        "Call the right tool now. If no tool can do it, tell the user plainly that you can't."
                    )
                    logger.info("Reply claimed an action with no tool call; asking again with tools %s", offered)
                    focus = TOOL_FOCUS.set(frozenset(offered))
                    try:
                        return self._loop_rounds(on_state, epoch, tool_schemas, offered, budget, memory_note, correction)
                    finally:
                        TOOL_FOCUS.reset(focus)
                reply_text = _usable_reply(response.text, all_tool_results)
                if not streamed:
                    self._emit_tokens(reply_text)
                self._remember("assistant", reply_text)
                self._set_state(on_state, AppState.IDLE)
                return AssistantReply(
                    text=reply_text,
                    state=AppState.IDLE,
                    created_at=datetime.now(timezone.utc),
                    tool_results=all_tool_results if all_tool_results else None,
                )

            # Process tool calls
            # Add the assistant message with tool calls to conversation
            # (some providers send partial text alongside tool calls)
            assistant_content = response.text or ""
            self._remember(
                "assistant",
                assistant_content,
                tool_calls=[
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                    for tool_call in response.tool_calls
                ],
            )

            for index, tool_call in enumerate(response.tool_calls):
                self._raise_if_cancelled()
                try:
                    result = self._execute_tool_call(tool_call, on_state)
                except _AskUser:
                    # Close every open tool call so the history stays valid for strict providers.
                    for skipped in response.tool_calls[index:]:
                        self._remember(
                            "tool",
                            json.dumps({"ok": False, "message": "Not run yet: waiting for the user to confirm."}),
                            tool_name=skipped.name,
                            tool_call_id=skipped.id,
                        )
                    raise
                all_tool_results.append({
                    "tool": tool_call.name,
                    "ok": result.ok,
                    "message": result.message,
                    "data": result.data,
                })
                # Add tool result to conversation as a tool message
                tool_response_text = json.dumps({
                    "ok": result.ok,
                    "message": result.message,
                    "data": result.data,
                }, default=str)
                self._remember(
                    "tool",
                    tool_response_text,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                )

        # If we exhausted rounds, force a final response without tools
        self._set_state(on_state, AppState.THINKING)
        messages = self._turn_messages(offered, _LONG_BUDGET, memory_note)
        response = self.provider.chat(messages, tools=None)
        reply_text = _usable_reply(response.text, all_tool_results) or "I completed the requested actions."
        self._emit_tokens(reply_text)
        self._remember("assistant", reply_text)
        self._set_state(on_state, AppState.IDLE)
        return AssistantReply(
            text=reply_text,
            state=AppState.IDLE,
            created_at=datetime.now(timezone.utc),
            tool_results=all_tool_results if all_tool_results else None,
        )

    def _execute_tool_call(
        self,
        tool_call: ToolCallRequest,
        on_state: StateCallback | None,
    ) -> ToolResult:
        """Look up, validate, permission-check, and execute a single tool call."""
        self._set_state(on_state, AppState.EXECUTING_TOOL)
        logger.info("Tool call requested: %s args=%s", tool_call.name, tool_call.arguments)

        tool = self.tools.get(tool_call.name)
        if tool is None:
            logger.warning("LLM requested unknown tool: %s", tool_call.name)
            return ToolResult(
                ok=False,
                message=f"Tool '{tool_call.name}' is not available. "
                        f"Available tools: {', '.join(self.tools.names())}",
            )

        # Permission check
        decision = self.permissions.decide(
            tool_call.name,
            tool.risk,
            tool.requires_confirmation,
        )
        if decision.action == PermissionAction.DENY:
            logger.warning("Tool %s denied: %s", tool_call.name, decision.reason)
            return ToolResult(ok=False, message=f"Permission denied: {decision.reason}")

        turn = _TURN.get()
        per_call = tool.needs_confirmation_for(tool_call.arguments)
        needs_confirm = decision.action == PermissionAction.CONFIRM or getattr(tool, "requires_pin", False) or per_call
        if needs_confirm:
            request = ConfirmationRequest(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                reason=decision.reason,
                summary=_confirmation_summary(tool, tool_call.arguments),
            )
            approved = False
            confirm = turn.confirm or self.confirm
            if turn.preapproved:
                approved = True
            elif confirm is None and turn.ask_on_reply:
                raise _AskUser(request, tool_call)
            elif confirm is not None:
                try:
                    approved = bool(confirm(request))
                except Exception:
                    logger.exception("Confirmation callback failed for %s", tool_call.name)
                    approved = False
            if approved and getattr(tool, "requires_pin", False):
                approved = bool(self.pin_check and self.pin_check())
                if not approved:
                    return ToolResult(ok=False, message="This action needs the phone PIN, so it was not run.")
            if not approved:
                logger.info("Tool %s was not confirmed", tool_call.name)
                return ToolResult(
                    ok=False,
                    message="This action was not confirmed, so it was not run.",
                )

        # Validate arguments
        try:
            validated_args = tool.validate_args(tool_call.arguments)
        except Exception as exc:
            logger.warning("Tool %s argument validation failed: %s", tool_call.name, exc)
            return ToolResult(
                ok=False,
                message=f"Invalid arguments for {tool_call.name}: {exc}. Correct the tool call and try again.",
            )

        # Execute
        try:
            result = tool.execute(validated_args)
            logger.info("Tool %s executed: ok=%s message=%s", tool_call.name, result.ok, result.message)
            if self.audit:
                self.audit(tool_call.name, {"ok": result.ok, "message": result.message})
            return result
        except Exception as exc:
            logger.exception("Tool %s execution failed", tool_call.name)
            return ToolResult(
                ok=False,
                message=f"Tool '{tool_call.name}' failed: {exc}",
            )

    def _is_reflex(self, text: str) -> bool:
        from core.command_parser import parse_command
        from core.hands import calendar_kind, spoken_math, wants_project, wants_reopen
        from core.personal import personal_statement, plain
        from core.reflex import about_me, battery_question, web_search_query, weather_place
        from core.when import parse_reminder, reminder_command, wants_reminder_list

        if personal_statement(text) is not None:
            return True
        body = plain(text).strip().rstrip("?.!")
        if "reminders" in self.tools.names() and (parse_reminder(body) is not None or wants_reminder_list(body) or reminder_command(body) is not None):
            return True
        if about_me(body) or (web_search_query(body) and "browser" in self.tools.names()) or (battery_question(body) and "system_info" in self.tools.names()):
            return True
        if weather_place(body) is not None or calendar_kind(body) or spoken_math(body) or wants_project(body) or wants_reopen(body):
            return True
        if instant_reply(body, self.config):
            return True
        return parse_command(body) is not None

    def _reflex_reply(self, text: str, on_state: StateCallback | None) -> AssistantReply | None:
        """Time, weather, apps, and media. None means this sentence needs the model."""
        from core.command_parser import confirmation_line, parse_command
        from core.reflex import cached_weather, is_calendar, store_weather, weather_place
        from tools.app_control import needs_confirmation

        from core.personal import plain

        body = text.strip()
        simple = plain(body)
        command = simple.rstrip("?.!")
        for fast in (self._personal_reply, self._manage_reminders, self._quick_reminder, self._reminder_list, self._about_me, self._web_search, self._battery):
            reply = fast(body, command, on_state)
            if reply is not None:
                return reply
        place = weather_place(command)
        if place is not None and not place and not self.config.default_city:
            return self._said(body, "Which city are you in? Say 'I live in London', for example, and I'll use it from now on.", on_state)
        if place is not None:
            line = cached_weather(place)
            if line is None:
                from tools.weather_tool import WeatherArgs, WeatherTool

                result = WeatherTool(self.config).execute(WeatherArgs(location=place or None))
                line = result.message if result.ok else "I don't have the weather right now."
                if result.ok:
                    store_weather(place, line)
            self._set_state(on_state, AppState.IDLE)
            self._remember("user", body)
            self._remember("assistant", line)
            return AssistantReply(text=line, state=AppState.IDLE, created_at=datetime.now(timezone.utc))

        if is_calendar(command):
            # A question about the calendar only reads it; it never opens an app.
            from core.calendar_ics import agenda
            from core.hands import calendar_kind

            kind = calendar_kind(command)
            url = getattr(self.config, "calendar_ics_url", None)
            if kind == "connect":
                line = (
                    "Paste your calendar's secret ICS link in Settings, under Ambient. In Google Calendar it's Settings, "
                    "your calendar, then 'Secret address in iCal format'. In Outlook, publish the calendar and copy the ICS link."
                )
            elif re.search(r"\btomorrow\b", command, re.IGNORECASE):
                line = agenda(url, (datetime.now().astimezone() + timedelta(days=1)).date())
            else:
                line = agenda(url)
            self._set_state(on_state, AppState.IDLE)
            self._remember("user", body)
            self._remember("assistant", line)
            return AssistantReply(text=line, state=AppState.IDLE, created_at=datetime.now(timezone.utc))

        from core.hands import make_project, reopen_last, spoken_math

        done = spoken_math(command) or reopen_last(command) or make_project(command)
        if done:
            self._set_state(on_state, AppState.IDLE)
            self._remember("user", body)
            self._remember("assistant", done)
            return AssistantReply(text=done, state=AppState.IDLE, created_at=datetime.now(timezone.utc))

        parsed = parse_command(command)
        if parsed is not None:
            self._remember("user", body)
            if needs_confirmation(parsed) and not VOICE_TURN.get():
                self._pending[_TURN.get().source] = {"kind": "fast", "args": parsed}
                line = confirmation_line(parsed)
                self._remember("assistant", line)
                self._set_state(on_state, AppState.IDLE)
                return AssistantReply(
                    text=line,
                    state=AppState.IDLE,
                    created_at=datetime.now(timezone.utc),
                    needs_confirm=True,
                )
            return self._run_fast_command(parsed, on_state)

        quick = instant_reply(command, self.config) or instant_reply(body, self.config)
        if not quick:
            return None
        self._set_state(on_state, AppState.IDLE)
        self._remember("user", body)
        self._emit_tokens(quick)
        self._remember("assistant", quick)
        return AssistantReply(text=quick, state=AppState.IDLE, created_at=datetime.now(timezone.utc))

    def _said(self, body: str, line: str, on_state: StateCallback | None, tool: str | None = None, ok: bool = True, message: str = "") -> AssistantReply:
        """Record a fast-path exchange and return it as the reply."""
        self._remember("user", body)
        self._remember("assistant", line)
        self._emit_tokens(line)
        self._set_state(on_state, AppState.IDLE)
        return AssistantReply(
            text=line,
            state=AppState.IDLE,
            error=not ok,
            created_at=datetime.now(timezone.utc),
            tool_results=[{"tool": tool, "ok": ok, "message": message or line}] if tool else None,
        )

    def _personal_reply(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        """'Call me Nick', 'I live in London', 'say sir at the end', 'from now on...' take effect at once."""
        from app.config import load_preferences, save_preferences
        from core.personal import personal_statements

        statements = personal_statements(body)
        if not statements:
            return None
        preferences = load_preferences()
        lines = [self._apply_personal(found, preferences) for found in statements]
        lines = [line for line in lines if line]
        if not lines:
            return None
        save_preferences(preferences)
        logger.info("Personal settings: %s", ", ".join(found.kind for found in statements))
        return self._said(body, " ".join(lines) if len(lines) > 1 else lines[0], on_state)

    def _apply_personal(self, found, preferences) -> str:
        """One setting into the live config and the saved preferences. Returns what to say."""
        if found.kind == "name":
            known = (self.config.display_name or "").lower() == found.value.lower()
            preferences.display_name = found.value
            self.config.display_name = found.value
            line = f"I know, {found.value}." if known else f"Nice to meet you, {found.value}. I'll call you {found.value}."
        elif found.kind == "city":
            preferences.default_city = found.value
            self.config.default_city = found.value
            line = f"Got it. I'll use {found.value} for the weather."
        elif found.kind == "suffix":
            preferences.reply_suffix = found.value
            self.config.reply_suffix = found.value
            line = "Understood. I'll end everything I say with that."
        elif found.kind == "stop_suffix":
            preferences.reply_suffix = None
            self.config.reply_suffix = None
            line = "Alright, I'll stop."
        elif found.kind == "forget_instructions":
            dropped = 0
            for item in self.memory.list_all() if self.memory is not None else []:
                if item.get("kind") == "instruction":
                    self.memory.forget(item["id"])
                    dropped += 1
            line = f"Done. I've dropped {dropped} standing instruction{'s' if dropped != 1 else ''}." if dropped else "There were no standing instructions to drop."
        else:
            if self.memory is None:
                return ""
            self.memory.remember(found.value, kind="instruction")
            line = "Understood. I'll do that from now on."
        return line

    def adopt_memories(self) -> list[str]:
        """Once at startup: settings the user told ORION about but that never took effect.

        Only fills what is empty (or the generic "Sir" as a name); a choice made in Settings wins.
        """
        if self.memory is None:
            return []
        from app.config import load_preferences, save_preferences
        from core.personal import personal_statements

        preferences = load_preferences()
        adopted = []
        for item in reversed(self.memory.list_all()):  # oldest first, so newer statements win
            if item.get("kind") == "instruction":
                continue
            for found in personal_statements(item["text"]):
                current = {
                    "name": (self.config.display_name or "").strip().lower() in {"", "sir", "madam"},
                    "city": not self.config.default_city,
                    "suffix": not getattr(self.config, "reply_suffix", None),
                }.get(found.kind)
                if current:
                    self._apply_personal(found, preferences)
                    adopted.append(f"{found.kind}={found.value}")
        if adopted:
            save_preferences(preferences)
            logger.info("Adopted from memory: %s", ", ".join(adopted))
        return adopted

    def _reminder_list(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        from ai.base_provider import ToolCallRequest
        from core.when import wants_reminder_list

        if "reminders" not in self.tools.names() or not wants_reminder_list(command):
            return None
        result = self._execute_tool_call(ToolCallRequest(id="fast", name="reminders", arguments={"action": "list"}), on_state)
        items = (result.data or {}).get("reminders") or []
        if not result.ok:
            line = result.message
        elif not items:
            line = "You have no reminders set."
        else:
            spoken = []
            now = datetime.now().astimezone()
            for item in items[:6]:
                due = datetime.fromisoformat(item["due_at"]).astimezone()
                when = due.strftime("%I:%M %p").lstrip("0")
                if due.date() != now.date():
                    when = ("tomorrow at " if (due.date() - now.date()).days == 1 else due.strftime("%A at ")) + when
                else:
                    when = f"at {when}"
                spoken.append(f"{item['title']} {when}")
            head = "You have one reminder: " if len(items) == 1 else f"You have {len(items)} reminders: "
            line = head + (", ".join(spoken[:-1]) + f", and {spoken[-1]}" if len(spoken) > 1 else spoken[0]) + "."
        return self._said(body, line, on_state, tool="reminders", ok=result.ok, message=result.message)

    def _about_me(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        from core.reflex import about_me

        line = about_me(command)
        return self._said(body, line, on_state) if line else None

    def _battery(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        from ai.base_provider import ToolCallRequest
        from core.reflex import battery_line, battery_question

        if "system_info" not in self.tools.names() or not battery_question(command):
            return None
        result = self._execute_tool_call(ToolCallRequest(id="fast", name="system_info", arguments={"category": "battery"}), on_state)
        line = battery_line((result.data or {}).get("battery") or {}) if result.ok else result.message
        return self._said(body, line, on_state, tool="system_info", ok=result.ok, message=result.message)

    def _web_search(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        from ai.base_provider import ToolCallRequest
        from core.reflex import web_search_query

        query = web_search_query(command)
        if not query or "browser" not in self.tools.names():
            return None
        result = self._execute_tool_call(ToolCallRequest(id="fast", name="browser", arguments={"action": "search", "query": query}), on_state)
        line = f"I've opened a web search for {query}." if result.ok else result.message
        return self._said(body, line, on_state, tool="browser", ok=result.ok, message=result.message)

    def _manage_reminders(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        """Cancel, move, snooze, and "when's my next one", on the reminders that really exist."""
        from core.when import new_time, pick, reminder_command, workdays_from

        tool = self.tools.get("reminders")
        found = reminder_command(command)
        if found is None or tool is None:
            return None
        repository = tool.repository
        upcoming = sorted(repository.list_open(), key=lambda item: item.due_at)
        now = datetime.now().astimezone()

        def when(item) -> str:
            local = item.due_at.astimezone()
            clock = local.strftime("%I:%M %p").lstrip("0")
            gap = (local - now).total_seconds()
            if gap < 3600:
                minutes = max(1, round(gap / 60))
                return f"in {minutes} minute{'s' if minutes != 1 else ''}"
            if local.date() == now.date():
                return f"at {clock}"
            if (local.date() - now.date()).days == 1:
                return f"tomorrow at {clock}"
            return f"on {local.strftime('%A')} at {clock}"

        def names() -> str:
            return ", ".join(f"{item.title} {when(item)}" for item in upcoming[:4])

        if found.kind == "next":
            line = f"Your next reminder is {upcoming[0].title}, {when(upcoming[0])}." if upcoming else "You have no reminders coming up."
            return self._said(body, line, on_state, tool="reminders")
        if found.kind == "snooze":
            target = repository.last_fired()
            if target is None or (datetime.now(timezone.utc) - (target.fired_at or target.due_at)).total_seconds() > 2 * 3600:
                return self._said(body, "There's nothing to snooze right now.", on_state)
            target.due_at = datetime.now(timezone.utc) + timedelta(minutes=found.minutes)
            target.status = "pending"
            repository.update(target)
            return self._said(body, f"Snoozed. I'll remind you about {target.title} again in {found.minutes} minutes.", on_state, tool="reminders")
        if not upcoming:
            return self._said(body, "You have no reminders right now.", on_state, tool="reminders")
        if found.kind == "cancel" and found.every:
            for item in upcoming:
                repository.delete(item.id)
            count = len(upcoming)
            return self._said(body, f"Done. I've cleared all {count} reminder{'s' if count != 1 else ''}.", on_state, tool="reminders")
        target = pick(upcoming, found.what)
        if target is None:
            asked = f" about {found.what}" if found.what else ""
            return self._said(body, f"I don't see a reminder{asked}. You have: {names()}.", on_state, tool="reminders")
        if found.kind == "cancel":
            repository.delete(target.id)
            return self._said(body, f"Cancelled: {target.title}, which was {when(target)}.", on_state, tool="reminders")
        moved = new_time(found.when, target.due_at, now=now, workdays=workdays_from(getattr(self.config, "work_days", None)))
        if moved is None:
            return self._said(body, f"When should I move {target.title} to?", on_state)
        target.due_at = moved.astimezone(timezone.utc)
        repository.update(target)
        return self._said(body, f"Moved: {target.title}, now {when(target)}.", on_state, tool="reminders")

    def _quick_reminder(self, body: str, command: str, on_state: StateCallback | None) -> AssistantReply | None:
        """'Remind me tomorrow at 9 to call the bank' runs the reminders tool directly, every time."""
        from ai.base_provider import ToolCallRequest
        from core.when import parse_reminder

        if "reminders" not in self.tools.names():
            return None
        from core.when import workdays_from

        days = workdays_from(getattr(self.config, "work_days", None))
        found = parse_reminder(command, workdays=days) or parse_reminder(body, workdays=days)
        if found is None:
            return None
        call = ToolCallRequest(
            id="fast",
            name="reminders",
            arguments={"action": "create", "title": found.title, "due_at": found.due.isoformat(), "recurrence": found.recurrence},
        )
        result = self._execute_tool_call(call, on_state)
        line = found.reply() if result.ok else result.message
        self._remember("user", body)
        self._remember("assistant", line)
        self._set_state(on_state, AppState.IDLE)
        return AssistantReply(
            text=line,
            state=AppState.IDLE,
            error=not result.ok,
            created_at=datetime.now(timezone.utc),
            tool_results=[{"tool": "reminders", "ok": result.ok, "message": result.message}],
        )

    def _run_fast_command(self, arguments: dict[str, Any], on_state: StateCallback | None, already_confirmed: bool = False) -> AssistantReply:
        from ai.base_provider import ToolCallRequest

        token = _TURN.set(replace(_TURN.get(), preapproved=already_confirmed))
        try:
            result = self._execute_tool_call(
                ToolCallRequest(id="fast", name="apps", arguments=arguments),
                on_state,
            )
        finally:
            _TURN.reset(token)
        self._remember("assistant", result.message)
        self._set_state(on_state, AppState.IDLE)
        return AssistantReply(
            text=result.message,
            state=AppState.IDLE,
            error=not result.ok,
            created_at=datetime.now(timezone.utc),
            tool_results=[{"tool": "apps", "ok": result.ok, "message": result.message}],
        )

    def _run_pending(self, pending: dict[str, Any], on_state: StateCallback | None) -> AssistantReply:
        if pending.get("kind") == "fast":
            return self._run_fast_command(pending["args"], on_state, already_confirmed=True)
        call = ToolCallRequest.model_validate(pending["call"])
        token = _TURN.set(replace(_TURN.get(), preapproved=True))
        try:
            result = self._execute_tool_call(call, on_state)
        finally:
            _TURN.reset(token)
        self._remember("assistant", result.message)
        self._set_state(on_state, AppState.IDLE)
        return AssistantReply(
            text=result.message,
            state=AppState.IDLE,
            error=not result.ok,
            created_at=datetime.now(timezone.utc),
            tool_results=[{"tool": call.name, "ok": result.ok, "message": result.message}],
        )

    def has_pending(self, source: str = "local") -> bool:
        return source in self._pending

    def history(self) -> list[ChatMessage]:
        return self.conversation.history()

    def clear_history(self) -> None:
        self.conversation.clear()
        if self.conversation_repository is not None:
            self.conversation_repository.clear()

    def _remember(self, role: str, content: str, **kwargs) -> ChatMessage:
        message = self.conversation.add(role, content, **kwargs)  # type: ignore[arg-type]
        if self.conversation_repository is not None:
            self.conversation_repository.save(message)
        return message

    def _error_reply(self, text: str, on_state: StateCallback | None) -> AssistantReply:
        lowered = text.lower()
        if "timed out" in lowered:
            text = "The local model is too slow right now. A free Groq key in Settings makes replies quick."
        elif VOICE_TURN.get() and "ollama" in lowered:
            text = "The model is offline. I can still do the simple things."
        self._set_state(on_state, AppState.ERROR)
        return AssistantReply(
            text=text,
            state=AppState.ERROR,
            error=True,
            created_at=datetime.now(timezone.utc),
        )

    def _capture_facts(self, text: str) -> None:
        if self.memory is None:
            return
        from core.memory_capture import capture

        try:
            for fact in capture(self.memory, text):
                logger.info("Remembered automatically: %s", fact)
        except Exception:
            logger.warning("Automatic memory capture failed", exc_info=True)

    def _recall_memory(self, text: str) -> str:
        """Facts worth knowing for this turn only. They are never left in the standing prompt."""
        if self.memory is None or len(text.split()) < 2:
            return ""
        try:
            hits = self.memory.recall(text, limit=4)
        except Exception:
            logger.warning("Memory recall failed", exc_info=True)
            return ""
        if not hits:
            return ""
        lines = "\n".join(f"- {item['text']}" for item in hits)
        return "Things you remember about the user. Use them only if they matter here:\n" + lines

    def _guarded(self, sink: Callable[[str], None]) -> Callable[[str], None]:
        def send(piece: str) -> None:
            self._raise_if_cancelled()
            sink(piece)

        return send

    def _emit_tokens(self, reply_text: str) -> None:
        """Replies that were not streamed (reflexes, tool turns) still reach a live listener, whole."""
        sink = _TURN.get().on_token or self.on_token
        if sink is None or not reply_text:
            return
        self._raise_if_cancelled()
        sink(reply_text)

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise CancelledError("Operation cancelled")

    @staticmethod
    def _set_state(on_state: StateCallback | None, state: AppState) -> None:
        if on_state:
            on_state(state)


_USELESS_REPLIES = {"none", "null", "n/a", "undefined", "nil"}


def _latest_user_text(assistant: "Assistant") -> str:
    return next((message.content for message in reversed(assistant.conversation.history()) if message.role == "user"), "")


def _usable_reply(text: str, tool_results: list[dict[str, Any]]) -> str:
    from core.hands import claims_unchecked_action

    cleaned = (text or "").strip()
    if cleaned.lower() in _USELESS_REPLIES:
        cleaned = ""
    if cleaned and claims_unchecked_action(cleaned, tool_results):
        return "I didn't do that. I only confirm something after it has actually run."
    if cleaned:
        return cleaned
    messages = [str(item.get("message") or "").strip() for item in tool_results if item.get("ok")]
    if messages:
        return "\n".join(messages)
    return "I'm here. Tell me what you want done."


def _clip(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if message.get("role") == "tool" and isinstance(content, str) and len(content) > _TOOL_OUTPUT_LIMIT:
        return {**message, "content": content[:_TOOL_OUTPUT_LIMIT] + " ...(truncated)"}
    return message


def _fit_budget(messages: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """Keep the system prompt, the whole current turn, and as much recent history as fits.

    A tool result is never kept without the assistant message that asked for it.
    """
    system = [item for item in messages if item.get("role") == "system"]
    rest = [_clip(item) for item in messages if item.get("role") != "system"]
    last_user = max((index for index, item in enumerate(rest) if item.get("role") == "user"), default=0)
    current, older = rest[last_user:], rest[:last_user]
    used = sum(len(str(item.get("content") or "")) + 40 for item in current)
    kept: list[dict[str, Any]] = []
    for item in reversed(older):
        size = len(str(item.get("content") or "")) + 40
        if used + size > max_chars:
            break
        kept.append(item)
        used += size
    kept.reverse()
    while kept and kept[0].get("role") == "tool":
        kept.pop(0)
    return system + kept + current


def _ask_line(request: ConfirmationRequest) -> str:
    from core.command_parser import confirmation_line

    if request.tool_name == "apps":
        return confirmation_line(request.arguments)
    details = ", ".join(f"{key} {value}" for key, value in request.arguments.items() if value not in ("", None))
    action = f"{request.tool_name} ({details})" if details else request.tool_name
    return f"That needs your OK first: {action}. Shall I go ahead? Reply yes or no."


def _confirmation_summary(tool: BaseTool, arguments: dict[str, Any]) -> str:
    details = ", ".join(f"{key}={value}" for key, value in arguments.items()) or "no arguments"
    return f"{tool.description}\n{tool.name} ({details})"


