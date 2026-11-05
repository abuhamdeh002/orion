"""Process-wide ORION runtime shared by the API and the desktop window."""

from __future__ import annotations

import hmac
import json
import logging
import queue
import threading
from datetime import datetime, timezone

from ai.factory import create_provider
from app.brand import NAME
from app.license import current_license
from app.config import AppConfig, load_config
from app.migrate import database_path, migrate_legacy
from app.paths import app_data_dir
from core.assistant import Assistant
from core.background import BackgroundTasks
from core.reminder_scheduler import ReminderScheduler
from service.auth import DeviceStore
from storage.conversation_repository import ConversationRepository
from storage.database import Database
from storage.memory_repository import MemoryRepository
from storage.reminder_repository import ReminderRepository
from tools.registry import create_default_registry
from voice.speech_output import SpeechOutput

logger = logging.getLogger("orion.service")
KILL = threading.Event()


class OrionRuntime:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        migrate_legacy(app_data_dir())
        self.database = Database(database_path(app_data_dir()))
        self.conversations = ConversationRepository(self.database)
        self.reminders = ReminderRepository(self.database)
        self.memory = MemoryRepository(self.database, self.config.ollama_base_url)
        self.devices = DeviceStore()
        self.events: list[dict] = []
        self._listeners: list[queue.Queue] = []
        self._listener_lock = threading.Lock()
        self.background = BackgroundTasks(self.push)
        self.tools = create_default_registry(
            self.config,
            reminder_repository=self.reminders,
            memory_repository=self.memory,
            background=self.background,
        )
        self.assistant = Assistant(
            self.config,
            create_provider(self.config),
            tools=self.tools,
            conversation_repository=self.conversations,
        )
        self.assistant.audit = self.audit
        self.assistant.pin_check = self._pin_ok
        self.assistant.memory = self.memory
        try:
            self.assistant.adopt_memories()
        except Exception:
            logger.warning("Could not adopt settings from memory", exc_info=True)
        self.pending_pin = False
        from core.when import workdays_from

        self.scheduler = ReminderScheduler(self.reminders, on_fire=self._reminder_fired, workdays=workdays_from(self.config.work_days))
        self.speaker = SpeechOutput(
            voice_id=self.config.tts_voice_id,
            rate=self.config.tts_rate,
            enabled=self.config.tts_provider != "none",
            provider=self.config.tts_provider,
        )
        from voice.conversation import VoiceConversation

        self.voice = VoiceConversation(self)
        # No global confirm: each entry point brings its own (voice asks out loud, the rest ask in the reply).
        self._pin = ""

    def reload_config(self) -> None:
        """Pick up new keys or settings without restarting the service."""
        self.config = load_config()
        self.assistant.apply_config(self.config, create_provider(self.config))

    def _reminder_fired(self, reminder, kind: str) -> None:
        """A reminder you can't hear is no reminder: chime, say it out loud, and tell every screen."""
        self.push(reminder.title, kind="reminder", data={"fire": kind, "id": reminder.id})
        if kind != "fired" or KILL.is_set():
            return
        threading.Thread(target=self._announce, args=(reminder.title,), name="OrionReminder", daemon=True).start()

    def _announce(self, title: str) -> None:
        from voice.chime import chime

        chime()
        line = {"Timer": "Time's up.", "Wake up": "Time to wake up.", "Alarm": "Your alarm."}.get(title, f"Reminder: {title}.")
        logger.info("Reminder announced: %s", title)
        if self.config.tts_provider != "none" and not KILL.is_set():
            self.voice.say_external(line)

    def push(self, text: str, kind: str = "note", data: dict | None = None) -> None:
        event = {
            "kind": kind,
            "text": text,
            "at": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        self.events.append(event)
        self.events[:] = self.events[-50:]
        with self._listener_lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=50)
        with self._listener_lock:
            self._listeners.append(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue) -> None:
        with self._listener_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def audit(self, tool_name: str, payload: dict) -> None:
        path = app_data_dir() / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"tool": tool_name, "at": datetime.now(timezone.utc).isoformat(), **payload})
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def set_pin(self, pin: str) -> None:
        self._pin = pin

    def _pin_ok(self) -> bool:
        """One phone approval allows exactly one PIN-protected action."""
        expected = self.config.orion_pin or ""
        if not expected or not self.pending_pin or not self._pin:
            return False
        ok = hmac.compare_digest(self._pin, expected)
        self.pending_pin = False
        self._pin = ""
        return ok

    def status(self) -> dict:
        ready, message = self.assistant.provider.health()
        return {
            "name": NAME,
            "ready": ready,
            "provider": message,
            "tools": self.tools.names(),
            "focus": self.config.focus_mode,
            "killed": KILL.is_set(),
            "license": current_license().plan,
            "license_notice": current_license().notice,
            # True while Ollama starts and the model loads (a minute on a small GPU): not the same as "no brain".
            "waking": (bool(getattr(self, "waking", False)) and not ready)
            or bool(getattr(getattr(self.assistant.provider, "doctor", None), "healing", False)),
        }

    def start_ambient(self) -> None:
        from web.desktop import open_shell

        from service.hotkey import listen
        from service.nudges import start as start_nudges
        from service.telegram_bridge import start as start_telegram
        from service.tray import start as start_tray

        url = f"http://{self.config.orion_host}:{self.config.orion_port}/"

        def _kill() -> None:
            KILL.set()
            self.speaker.stop()
            self.voice.hush()
            self.assistant.cancel()
            self.background.stop_all()

        listen(lambda: open_shell(url), on_kill=_kill)
        start_nudges(self)
        start_telegram(self)
        start_tray(self)
        self.scheduler.catch_up()
        self.warm_model_async()
        self.voice.start()
        from app.license import current_license

        license_state = current_license()
        logger.info("License: %s", license_state.reason)
        if self.config.orion_relay_url and self.config.orion_account_token:
            from service.relay_client import RelayClient

            RelayClient(
                self,
                self.config.orion_relay_url,
                self.config.orion_account_token,
                account=self.config.orion_account_id,
            ).start()
        open_shell(url)

    def warm_model_async(self) -> None:
        """Once per process: make sure Ollama is up and the model is loaded."""
        if getattr(self, "_warming", False):
            return
        self._warming = True
        threading.Thread(target=self._warm_model, name="OrionWarm", daemon=True).start()

    def _warm_model(self) -> None:
        """Start Ollama if it is installed but not running, then load the model.

        Runs after the microphone is already open, so a slow load cannot block a turn.
        """
        local = getattr(self.assistant.provider, "local", None)
        if local is None:
            return
        doctor = getattr(self.assistant.provider, "doctor", None)
        self.waking = True
        if doctor is not None:
            doctor.begin()
        try:
            self._load_local(local)
        finally:
            self.waking = False
            if doctor is not None:
                doctor.done()
            refresh = getattr(self.assistant.provider, "local_health", None)
            if refresh is not None:
                refresh(fresh=True)

    def _load_local(self, local) -> None:
        import httpx

        from ai.ollama_provider import NUM_CTX
        from service.ollama_boot import ensure_ollama

        if not ensure_ollama(local.base_url):
            logger.warning("Ollama is not available; replies will use cloud models if keys are set")
            return
        refresh = getattr(self.assistant.provider, "local_health", None)
        if refresh is not None:
            refresh(fresh=True)
        try:
            httpx.post(
                f"{local.base_url}/api/generate",
                json={
                    "model": local.model,
                    "prompt": "ok",
                    "stream": False,
                    "keep_alive": "2h",
                    "options": {"num_predict": 1, "num_ctx": NUM_CTX},
                },
                timeout=240,  # a first load on a new GPU setup took 63 s
            )
            logger.info("Model is warm (%s)", local.model)
        except Exception as exc:
            logger.warning("Model warmup skipped: %s", exc)


_runtime: OrionRuntime | None = None
_lock = threading.Lock()


def get_runtime() -> OrionRuntime:
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = OrionRuntime()
        return _runtime
