# Building ORION for Windows

ORION ships as a one-folder PyInstaller build of the service (`build/orion.spec`). It bundles the web UI and the voice models.

## Build

From the repository folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

It builds the web UI, then `dist\ORION\ORION.exe` with PyInstaller (`build/orion.spec`), then the installer `dist\installer\ORION-Setup-<version>.exe` with Inno Setup 6 if it's installed (`winget install JRSoftware.InnoSetup`).

How the app launches:

| Command | What happens |
|---|---|
| `ORION.exe` | Starts the service and opens the native window. If ORION is already running, it only opens the window. |
| `ORION.exe --background` | Starts quietly. Sign-in autostart uses this. |
| `ORION.exe --window <url>` | The window on its own (the service starts it). |

The build is windowed (no console). Logs go to `%LOCALAPPDATA%\ORION\logs`.

A packaged build keeps settings, the database, and the license under `%LOCALAPPDATA%\ORION`. An older `%LOCALAPPDATA%\JARVIS2` folder is renamed on first launch.

Tested on 2026-11-05: built (344 MB folder, 119 MB installer), installed silently, started, answered, fired a timer with the chime and voice, opened the native window, and uninstalled with no files, shortcuts, or registry entries left.

## Clean-machine checklist

- [ ] The folder starts without a Python install.
- [ ] With no `.env` and no Ollama, the UI opens and says which key or service to set up.
- [ ] Put secrets in the user environment, or in a `.env` next to `ORION.exe`.
- [ ] A microphone and speakers work when the machine has them.
- [ ] OCR works only if Tesseract is installed (UB Mannheim build, on `PATH` or in `C:\Program Files\Tesseract-OCR`).
- [ ] Weather works with no key (Open-Meteo). Telegram stays off until its token is set.

## Troubleshooting

- **PyAudio:** install the wheel for Python 3.12 64-bit.
- **Tesseract:** ORION reports a clear error when the binary is missing.
- **Antivirus flags the exe:** PyInstaller bootloaders are sometimes flagged. Code-sign the build before sharing it.

## Product install

`build\install.ps1` asks for a license key and stores it at `%LOCALAPPDATA%\ORION\license.key`. Without a key, ORION runs a 14-day trial. The trial start is also kept in `HKCU\Software\ORION`, so deleting `trial.txt` does not restart it.

What a license allows:

| State | On the PC (chat, voice, tools) | Phone (paired devices, pairing) | Cloud relay |
|---|---|---|---|
| Trial (14 days) | yes | yes | yes |
| Lifetime | yes | yes | no |
| Cloud / bundle | yes | yes | yes |
| Expired | yes | no (HTTP 402) | no |

For your own PCs, `python scripts/mint_license.py` signs a key with the private key in `cloud/site/.dev.vars` and installs it.

License keys are Ed25519-signed. The public key is in `app/license.py`. The private key exists only as the site's `LICENSE_PRIVATE_HEX` secret: `cloud/site/.dev.vars` locally (gitignored), and a Worker secret in production. It was rotated on 2026-11-04 after the old one was found in source.

- **Relay:** `cloud/relay` needs a `RELAY_SECRET` of at least 32 characters. The PC connects with `ORION_RELAY_URL`, `ORION_ACCOUNT_ID`, and `ORION_ACCOUNT_TOKEN`. During development, mint tokens with `node cloud/relay/scripts/token.mjs <account>`.
- **Site:** `cloud/site` needs `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the price ids. See `.dev.vars.example` in each folder.
- **Android:** `android/` builds with Android Studio.
