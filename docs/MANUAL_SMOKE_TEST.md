# Manual smoke test

Automated tests do not replace these checks. Run them with `python -m service`, or with `dist\ORION\ORION.exe`.

## Startup

1. With Ollama stopped and no cloud keys, start ORION. The UI opens and says what to set up. Nothing crashes.
2. Start Ollama, or add a `GROQ_API_KEY`, and restart. The health line names the live backend.

## Chat and tools

1. Ask for the time, the battery, and a web search. Search opens the browser.
2. Ask to lock the PC, then decline. The PC does not lock.
3. "Remind me in one minute to stretch": the reminder fires once.
4. "Remember my sister is Lina". Restart, then ask "who's my sister?".

## Voice

1. Say "Hey Orion, what time is it?". The reply is spoken.
2. Talk over the reply. ORION stops and listens.
3. Play a video near the mic for five minutes. ORION does not answer it.
4. Press `Ctrl+Alt+Esc`, then say "Hey Orion". Nothing runs until you resume.

## Security

1. From another site's devtools, run `new WebSocket("ws://127.0.0.1:8765/ws")`. It is refused.
2. `curl -H "X-Forwarded-For: 1.2.3.4" http://127.0.0.1:8765/skills` returns 401.

## Phone

1. Pair from the PC and scan the QR code. Chat works from the phone.
2. Revoke the device from the PC. The phone gets 401.

## Packaged build

1. Build with [BUILD.md](BUILD.md).
2. Run `dist\ORION\ORION.exe` on a machine (or Windows Sandbox) without this virtual environment.
