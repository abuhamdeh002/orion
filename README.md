# ORION

A personal, local-first assistant for Windows. One always-on service on your PC handles typed and spoken chat, runs allowlisted tools (apps, reminders, weather, system status, memory, media), and is reachable from the browser, your phone, and Telegram.

> Formerly *Jarvis* / *Jarvis 2.0*. Old data (`jarvis.db`, `%LOCALAPPDATA%\JARVIS2`, autostart entries) is migrated automatically on first start; see `app/migrate.py`.

## Requirements

- Windows 10/11, Python 3.12
- A brain, at least one of:
  - [Ollama](https://ollama.com) running locally (private, free), and/or
  - a free `GROQ_API_KEY` and/or `GEMINI_API_KEY` as cloud fallback
- Optional: a microphone, [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for reading images and the screen, and `TELEGRAM_BOT_TOKEN`

## Run it

From the repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then fill in what you use
python -m service           # starts ORION and opens the web UI
```

- `Win+Alt+Space` opens the UI. `Ctrl+Alt+Esc` is the kill switch: it stops speech, voice, tools, the relay, and Telegram until you resume.
- Say **"Hey Orion"** to talk. The PC mic stays open, and speech is transcribed locally with faster-whisper.
- `PRIVATE_MODE=true` keeps every request on the local model.
- `python -m service --install-autostart` starts ORION at login.

## Phone

From the PC, `POST /pair` returns a pairing link and a QR code. The token rides in the link's `#fragment`, so it never reaches server logs. Open it over Tailscale HTTPS (`tailscale serve`), not the public internet. Proxied requests always need a paired token. An iPhone Shortcut can `POST /chat` with `Authorization: Bearer <token>` and `{"text": "..."}`. The Android app (`android/`) can also connect through the cloud relay (`cloud/relay`).

## What it will not do

- Run model-written Python or shell commands
- Open `javascript:` or `file:` URLs
- Send a message, lock the PC, click inside another app, overwrite the clipboard, or open an app outside a short safe list without confirmation
- Shut down or restart without confirmation *and* a one-time PIN approval from a paired phone (`ORION_PIN`)
- Accept requests from other websites (Origin check), DNS-rebinding hosts (Host check), or unpaired remote devices
- Invent weather, files, or tool results

## Tests

```powershell
pytest
```

Network calls and hardware are mocked. The web UI, relay, and site have their own tests (`npm test` in `cloud/relay` and `cloud/site`).

## More

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit
- [docs/BUILD.md](docs/BUILD.md): packaging and the product install
- [docs/MANUAL_SMOKE_TEST.md](docs/MANUAL_SMOKE_TEST.md): checks to run by hand
- [FEATURE_STATUS.md](FEATURE_STATUS.md): what is implemented and tested
