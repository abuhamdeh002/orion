# Architecture

ORION is one process: the service. Every way of talking to it goes through the same runtime and the same assistant.

```
Browser / PWA (web/)  ─┐
Android app ── relay ──┤                      ┌─ ModelRouter: Ollama → Groq → Gemini
Telegram bot ──────────┼─► service/api.py ──► Assistant ─┼─ ToolRegistry + PermissionGate
iPhone Shortcut ───────┤   (guard.py checks)  (core/)    └─ Memory (SQLite)
"Hey Orion" (voice/) ──┘
                                    OrionRuntime (service/runtime.py) owns:
                                    database, reminders, memory, voice loop,
                                    speaker, tray, hotkeys, relay client
```

- **service/**: FastAPI app, the runtime singleton, pairing (`auth.py`), request safety (`guard.py`), phone commands, relay client, tray, hotkeys, and Telegram.
- **core/**: the assistant turn loop, quick pre-model replies (reflexes), confirmation, and reminder scheduling.
- **ai/**: providers (OpenAI-compatible and Ollama) and the router that picks local or cloud.
- **tools/**: everything the model can do. Each tool has a Pydantic schema, a risk level, and optional per-call confirmation (`needs_confirmation_for`).
- **voice/**: mic stream with Silero VAD, local speech recognition, wake handling, and TTS (Kokoro, edge-tts, SAPI).
- **storage/**: SQLite at `data/orion.db` (or `%LOCALAPPDATA%\ORION\orion.db` when packaged) for messages, reminders, and memories.
- **web/**: the React PWA served by the service.
- **cloud/relay**: a Cloudflare Durable Object that lets the phone reach the PC from anywhere. Tokens are per account and role.
- **cloud/site**: the landing page, portal, admin, and Stripe webhook that mints licenses.
- **android/**: the phone client.

The model never runs Python or shell. Tool arguments are validated. Risky actions wait for a confirmation. If nothing answers, the action is denied.

Secrets stay in environment variables (`.env`; `.dev.vars` for the cloud workers). Preferences live in `settings.json`.

The legacy desktop window (`python main.py`, `ui/`) is being retired in favour of the service and web UI.
