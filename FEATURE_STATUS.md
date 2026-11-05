# ORION: feature status

Status values: **implemented**, **tested**, **partially implemented**, **not implemented**, **unverified** (written but not run on real hardware or a real build here).

| Feature | Status | Notes |
|---|---|---|
| One app: service + web UI | implemented, tested | `python -m service` or `python main.py`. PySide6 window retired. The window is pywebview (own process) or the browser |
| Legacy Jarvis migration | implemented, tested | `app/migrate.py`: database and WAL, history rename (once), app data folder, logs, autostart |
| Local API safety | implemented, tested | Host, Origin, and proxy checks (`service/guard.py`). Pairing token in the URL fragment. PIN approvals are one-shot |
| Model routing | implemented, tested | Ollama first for chat. Groq, then Gemini, for tool turns and as fallback. Clear message when no model exists. `PRIVATE_MODE` forces local |
| Ollama autostart | implemented, tested | Starts `ollama serve` and waits up to 90 s (66 s measured on the RTX 3050 PC). One `num_ctx` everywhere, so the model is not reloaded between voice and typed turns. Surviving an ORION restart is unverified |
| First-run setup | implemented, tested | Web card plus `/setup` (PC only) saves free keys to `.env` and switches without a restart |
| Tool gating | implemented, tested | Whole-word rules per tool. The local model gets only the relevant tools |
| Per-source turns | implemented, tested | Voice confirms by voice. Web, phone, and Telegram are asked in the reply. Requests queue instead of cancelling |
| Long-term memory | implemented, tested | SQLite FTS5 recall survives restarts. Embeddings are an optional boost. Facts stated in passing are captured (`kind=auto`) |
| Streaming | implemented, tested | Typed replies stream over `/ws`. Spoken replies start at the first full sentence; slow turns say "One moment." first. Tool turns still wait for the model's tool choice |
| Typed conversations | implemented, tested | History budget keeps tool calls valid for strict providers |
| Reflexes (pre-model) | implemented, tested | False positives fixed: calendar, folders, reopen, phone numbers, "open it again" |
| Voice wake and gating | implemented, tested | Name required. 20 s awake, 8 s follow-up. Room noise from the old log is ignored. Kill switch silences the mic |
| Speech input | implemented, tested | faster-whisper `base.en` locally. Room audio is never sent to Google |
| Speech output | implemented, tested | Kokoro (8 local voices) or Edge (7 online). Natural pace (1.0, was 1.22), punctuation-aware pauses, times/dates/units read as a person would. The chosen voice picks the engine |
| Wake word (acoustic) | not implemented | Optional `data/models/hey_orion.onnx` is loaded if you train one |
| Images | implemented | Web image button (camera on phones) plus `/image` OCR. Tesseract required |
| Reminders / timers | implemented, tested | Understood without the model (`core/when.py`): seconds, clock times, "tomorrow at 9", weekdays, "every day". When one fires: chime, spoken aloud, toast in the page, desktop notification. "What reminders do I have" reads the real list |
| Weather, music, messaging, system info | implemented, tested | As before |
| Cloud relay | implemented, tested | HMAC token per account and role. State persisted. PC client sends role and account and honours the kill switch |
| Site / billing | implemented, tested | D1, deployable worker, session-bound portal, admin token, 35-day cloud licenses renewed on `invoice.paid`. Not deployed here |
| License keys | implemented, tested | Ed25519. Key rotated 2026-11-04. Private key is a secret only. After the trial, the PC keeps working; phone access and the relay stop. Trial start is also kept in the registry. `scripts/mint_license.py` for your own PCs |
| Android app | implemented, unverified | Pairing link, persistent socket, presence, Android 14 tile fix, PIN shutdown, widget refresh. Not compiled here (no Gradle or SDK) |
| Packaging | implemented, tested on this PC | `scripts/build.ps1` → `dist\ORION` (344 MB, windowed) → `dist\installer\ORION-Setup-2.1.0.exe` (119 MB). Built, installed silently, started, answered, uninstalled with nothing left (2026-11-05). Launching opens the native window; sign-in autostart runs `--background`; a second launch only opens the window. Not yet tried on a clean machine; the Kokoro voice (350 MB) downloads on first start |
| Phone pairing link | implemented, tested | Uses `ORION_PUBLIC_URL` or this PC's Tailscale name. With neither, no token is made and the page says what to set up |
| Test isolation | implemented, tested | Tests use a temporary data folder and never read the real `.env` (`ORION_DATA_DIR`, `ORION_ENV_FILE`) |
| Voice picker | implemented, tested | Settings: preview any voice in the browser, choose it, set the pace (`/voice/voices`, `/voice/sample`, `/voice/choose`) |
| Web design | implemented, checked on screen | "Night over Orion": live constellation per state, Instrument Serif + Geist (bundled, offline), night and dawn themes |
| Honest actions | implemented, tested | A reply that claims an action with no tool behind it gets one more round with the right tools |
| Personal settings | implemented, tested | "Call me Nick", "I live in London", "say sir at the end", "from now on..." take effect immediately and persist |
| Self-knowledge | implemented, tested | How to stop ORION and what it can do are answered from facts, not guessed |
| Real-world benchmark | implemented | `python -m evals.assistant_bench`: 25 everyday requests through the real model, checked by outcome |
| Today home screen | implemented, checked on screen | Upcoming reminders with live countdown rings (snooze, done), weather, live CPU and memory, what ORION remembers (`/today`, `/reminders`) |
| Command palette | implemented, checked on screen | Ctrl+K: every action, page, theme and accent; anything else is sent to ORION |
| Ambient clock | implemented, checked on screen | Night-sky clock with the next reminder and the weather; opens from the rail or after three quiet minutes (Settings) |
| Voice-reactive constellation | implemented, tested | `/voice/levels` streams mic and voice loudness; the figure moves with real sound (an online voice falls back to a speech rhythm) |
| Accent palettes | implemented, checked on screen | Rigel, Betelgeuse, Nebula, Aurora, for both night and light |
| Rich replies | implemented, checked on screen | Lists, bold, code and links rendered safely; Copy and Read aloud (`/voice/say`) on every reply |
| Waking state | implemented, checked on screen | While the model loads, ORION says it's waking (and what already works) instead of showing setup |
| Voice conversation | implemented, checked on screen | Full-screen voice mode (round voice button, or Ctrl+K): keeps listening without the wake word, big live captions, Interrupt and End |
| Modern chat | implemented, checked on screen | Growing prompt box (Enter sends, Shift+Enter new line), shimmering Thinking, follow-up suggestions, New chat, glowing screen edge while active |
| Self-healing brain | implemented, tested | A local reply over 30 s or a server error unloads and reloads the model in the background (`ai/doctor.py`); requests while it wakes or heals wait up to 75 s |
| Managing reminders | implemented, tested | Cancel, move (keeps the day), snooze, "when is my next", weekday repeats (working week is a setting) |
| Calendar | implemented, tested | Read only from the secret ICS link: time zones, all-day, repeats. Asking never opens an app |
| Memories take effect | implemented, tested | Name, city and reply ending said in passing are applied; a one-time catch-up at start fills empty settings |
| Kill switch | implemented, checked on screen | Two taps to stop; not in the phone bottom bar; the home screen offers to turn ORION back on |
