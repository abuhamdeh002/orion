"""Local ORION HTTP and WebSocket API. Bind to localhost unless Tailscale is explicit."""

from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.brand import NAME, TAGLINE
from app.license import TRIAL_ENDED_DETAIL, license_gate
from service.guard import bearer, host_allowed, is_local, origin_allowed
from service.reach import UNREACHABLE, public_base
from service.runtime import KILL, get_runtime
from skills.registry import load_skills

WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
WEB_PUBLIC = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title=NAME)
_clients: set[WebSocket] = set()


def _local(request: Request) -> bool:
    return is_local(request.client.host if request.client else "", request.headers)


@app.middleware("http")
async def require_device(request: Request, call_next):
    headers = request.headers
    if not host_allowed(headers.get("host")):
        return JSONResponse({"detail": "Unknown host."}, status_code=421)
    if not origin_allowed(headers.get("origin"), headers.get("host")):
        return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
    path = request.url.path
    if request.method == "GET" and (path == "/" or path.startswith("/assets") or "." in path.rsplit("/", 1)[-1]):
        return await call_next(request)
    if path == "/health" or (path == "/pair" and request.method == "POST"):
        return await call_next(request)
    if not _local(request):
        if not get_runtime().devices.valid(bearer(headers)):
            return JSONResponse({"detail": "Pair this device first."}, status_code=401)
        if not license_gate().allows_phone:
            return JSONResponse({"detail": TRIAL_ENDED_DETAIL, "license": "expired"}, status_code=402)
    return await call_next(request)


class ChatIn(BaseModel):
    text: str
    # Replies to the web or phone are not read out on the PC unless asked for.
    speak: bool = False


class PairIn(BaseModel):
    name: str = "phone"


class PinIn(BaseModel):
    pin: str
    approved: bool = False


class PersonaIn(BaseModel):
    persona: str = "calm"
    display_name: str | None = None
    focus_mode: bool | None = None
    calendar_ics_url: str | None = None


@app.get("/health")
def health() -> dict:
    return get_runtime().status() | {"tagline": TAGLINE}


@app.get("/skills")
def skills() -> list[dict]:
    runtime = get_runtime()
    return load_skills(runtime.tools.names(), runtime.config)


@app.get("/memory")
def memory() -> list[dict]:
    return get_runtime().memory.list_all()


class MemoryIn(BaseModel):
    text: str


@app.post("/memory")
def add_memory(body: MemoryIn) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Memory text is empty.")
    return {"id": get_runtime().memory.remember(text)}


@app.delete("/memory/{memory_id}")
def forget(memory_id: str) -> dict:
    return {"forgotten": get_runtime().memory.forget(memory_id)}


@app.get("/pair")
def list_paired(request: Request) -> dict:
    if not _local(request):
        raise HTTPException(status_code=403, detail="Pair from the PC itself.")
    return {"devices": get_runtime().devices.list_devices()}


@app.delete("/pair/{tail}")
def revoke_paired(tail: str, request: Request) -> dict:
    if not _local(request):
        raise HTTPException(status_code=403, detail="Pair from the PC itself.")
    return {"revoked": get_runtime().devices.revoke_tail(tail)}


@app.post("/pair")
def pair(body: PairIn, request: Request) -> dict:
    if not _local(request):
        raise HTTPException(status_code=403, detail="Pair from the PC itself.")
    if not license_gate().allows_phone:
        raise HTTPException(status_code=402, detail=TRIAL_ENDED_DETAIL)
    runtime = get_runtime()
    # 127.0.0.1 on a phone is the phone itself, so a link is only made for a Tailscale or public address.
    # No address means no token either: a device key nobody can use should not exist.
    base = public_base(runtime.config)
    result: dict = {"name": NAME, "reachable": base is not None, "detail": None if base else UNREACHABLE}
    if base:
        token = runtime.devices.pair(body.name)
        # The token rides in the fragment, which browsers never send to a server or write to access logs.
        link = f"{base}/#token={token}"
        result.update(token=token, link=link, qr_png_base64=_qr(link))
    phone = phone_pair_link(runtime.config)
    if phone:
        result["phone_link"] = phone
        result["phone_qr_png_base64"] = _qr(phone)
    return result


def phone_pair_link(config) -> str | None:
    """orion://pair?relay=...&account=...&token=... for the Android app, when the cloud relay is configured."""
    from urllib.parse import urlencode

    if not (config.orion_relay_url and config.orion_account_id and config.orion_phone_token):
        return None
    query = urlencode({"relay": config.orion_relay_url, "account": config.orion_account_id, "token": config.orion_phone_token})
    return f"orion://pair?{query}"


@app.post("/pin")
def pin(body: PinIn, request: Request) -> dict:
    runtime = get_runtime()
    if not runtime.devices.valid(bearer(request.headers)):
        raise HTTPException(status_code=401, detail="Phone token required.")
    runtime.set_pin(body.pin)
    runtime.pending_pin = body.approved
    return {"ok": True}


class SetupIn(BaseModel):
    groq_api_key: str | None = None
    gemini_api_key: str | None = None


@app.get("/setup")
def setup_status() -> dict:
    """Which brains are live, so the UI can say exactly what is missing."""
    runtime = get_runtime()
    provider = runtime.assistant.provider
    backends = provider.backends() if hasattr(provider, "backends") else {}
    ready, _message = provider.health()
    return {
        "ready": ready,
        "backends": backends,
        "keys": {"groq": bool(runtime.config.groq_api_key), "gemini": bool(runtime.config.gemini_api_key)},
        "links": {
            "groq": "https://console.groq.com/keys",
            "gemini": "https://aistudio.google.com/apikey",
            "ollama": "https://ollama.com/download",
        },
    }


@app.post("/setup")
def setup_save(body: SetupIn, request: Request) -> dict:
    """Save free cloud keys to .env and switch to them at once. Only from the PC itself."""
    from app.env_file import set_env_values
    from app.paths import env_file

    if not _local(request):
        raise HTTPException(status_code=403, detail="Change keys from the PC itself.")
    values = {}
    if body.groq_api_key is not None:
        values["GROQ_API_KEY"] = body.groq_api_key.strip()
    if body.gemini_api_key is not None:
        values["GEMINI_API_KEY"] = body.gemini_api_key.strip()
    if not values:
        raise HTTPException(status_code=400, detail="Nothing to save.")
    try:
        set_env_values(env_file(), values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_runtime().reload_config()
    return setup_status()


@app.get("/persona")
def read_persona() -> dict:
    config = get_runtime().config
    return {
        "persona": config.persona,
        "display_name": config.display_name,
        "focus_mode": config.focus_mode,
        "calendar_ics_url": config.calendar_ics_url,
    }


@app.post("/persona")
def persona(body: PersonaIn) -> dict:
    from app.config import load_preferences, save_preferences

    preferences = load_preferences()
    preferences.persona = body.persona.strip() or "calm"
    if body.display_name is not None:
        preferences.display_name = body.display_name.strip() or None
    if body.focus_mode is not None:
        preferences.focus_mode = body.focus_mode
    if body.calendar_ics_url is not None:
        preferences.calendar_ics_url = body.calendar_ics_url.strip() or None
    save_preferences(preferences)
    runtime = get_runtime()
    runtime.config.persona = preferences.persona
    runtime.config.display_name = preferences.display_name
    runtime.config.focus_mode = preferences.focus_mode
    runtime.config.calendar_ics_url = preferences.calendar_ics_url
    return {"persona": preferences.persona, "focus_mode": preferences.focus_mode}


def _actions(reply) -> list[dict]:
    return [
        {"tool": item.get("tool"), "ok": bool(item.get("ok")), "message": item.get("message")}
        for item in reply.tool_results or []
    ]


@app.post("/chat")
def chat(body: ChatIn) -> dict:
    if KILL.is_set():
        raise HTTPException(status_code=423, detail="Kill switch is on.")
    runtime = get_runtime()
    reply = runtime.assistant.handle_user_message(body.text, source="web", ask_on_reply=True)
    if (body.speak or runtime.config.speak_replies) and reply.text:
        runtime.voice.say_external(reply.text)
    return {
        "text": reply.text,
        "error": reply.error,
        "state": reply.state.value,
        "actions": _actions(reply),
        "confirm": bool(reply.needs_confirm),
    }


@app.get("/voice")
def voice_status() -> dict:
    return get_runtime().voice.status()


@app.post("/voice/awake")
def voice_awake() -> dict:
    runtime = get_runtime()
    runtime.voice.awake()
    runtime.voice.start()
    return runtime.voice.status()


@app.post("/voice/stop")
def voice_stop() -> dict:
    runtime = get_runtime()
    runtime.voice.hush()
    return runtime.voice.status()


class VoiceChoiceIn(BaseModel):
    voice: str
    rate: int | None = None


def _current_voice() -> str:
    from voice.kokoro_engine import DEFAULT_VOICE
    from voice.speech_output import DEFAULT_NEURAL_VOICE

    runtime = get_runtime()
    chosen = runtime.speaker.voice_id
    if chosen:
        return chosen
    return DEFAULT_NEURAL_VOICE if runtime.config.tts_provider == "edge" else DEFAULT_VOICE


@app.get("/voice/voices")
def voice_list() -> dict:
    from voice.speech_output import voice_catalog

    return {"current": _current_voice(), "rate": get_runtime().speaker.rate, "voices": voice_catalog()}


@app.get("/voice/sample")
def voice_sample(voice: str, rate: int = 180) -> Response:
    """A short preview the browser plays, so voices can be compared by ear before choosing."""
    from voice.speech_output import render_sample, voice_catalog

    if voice not in {item["id"] for item in voice_catalog()}:
        raise HTTPException(status_code=404, detail="Unknown voice.")
    try:
        audio, media = render_sample(voice, max(120, min(240, rate)))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"That voice is not available right now ({exc}).") from exc
    return Response(content=audio, media_type=media, headers={"Cache-Control": "no-store"})


@app.post("/voice/choose")
def voice_choose(body: VoiceChoiceIn) -> dict:
    from app.config import load_preferences, save_preferences
    from voice.speech_output import voice_catalog

    if body.voice not in {item["id"] for item in voice_catalog()}:
        raise HTTPException(status_code=404, detail="Unknown voice.")
    runtime = get_runtime()
    preferences = load_preferences()
    preferences.tts_voice_id = body.voice
    runtime.speaker.voice_id = body.voice
    if body.rate is not None:
        preferences.tts_rate = max(120, min(240, body.rate))
        runtime.speaker.rate = preferences.tts_rate
    save_preferences(preferences)
    return voice_list()


@app.post("/listen")
def listen_mic() -> dict:
    from voice.speech_input import SpeechInput

    runtime = get_runtime()
    if runtime.voice.phase not in {"off"}:
        # The always-on microphone already holds the device; opening a second one crashes some drivers.
        runtime.voice.awake()
        return {"ok": True, "text": "", "awake": True}
    ear = SpeechInput(
        device_index=runtime.config.microphone_device_index,
        enabled=runtime.config.stt_provider != "none",
    )
    ok, text = ear.listen_once(timeout=8, phrase_time_limit=12)
    return {"ok": ok, "text": text}


@app.post("/speak")
def speak(body: ChatIn) -> dict:
    speaker = get_runtime().speaker
    if not body.text.strip():
        speaker.stop()
        return {"spoken": False}
    return {"spoken": speaker.speak(body.text)}


@app.post("/kill")
def kill() -> dict:
    runtime = get_runtime()
    KILL.set()
    runtime.speaker.stop()
    runtime.voice.hush()
    runtime.assistant.cancel()
    runtime.background.stop_all()
    return {"killed": True}


@app.post("/resume")
def resume() -> dict:
    KILL.clear()
    return {"killed": False}


@app.get("/events")
def events() -> list[dict]:
    return get_runtime().events


@app.get("/events/stream")
async def event_stream(request: Request) -> StreamingResponse:
    runtime = get_runtime()
    listener = runtime.subscribe()

    async def generate():
        try:
            yield "event: ready\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    item = await asyncio.to_thread(listener.get, True, 15)
                except Exception:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {item['kind']}\ndata: {json.dumps(item)}\n\n"
        finally:
            runtime.unsubscribe(listener)

    return StreamingResponse(generate(), media_type="text/event-stream")


class ImageIn(BaseModel):
    data_base64: str
    filename: str = "photo.jpg"
    action: str = "ocr"


_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_IMAGE_LIMIT = 10 * 1024 * 1024


@app.post("/image")
def image(body: ImageIn) -> dict:
    """A photo or picture the person chose, read with OCR (or described when a vision model is set)."""
    from datetime import datetime

    from app.paths import app_data_dir
    from tools.vision_tool import VisionArgs, VisionTool

    if KILL.is_set():
        raise HTTPException(status_code=423, detail="Kill switch is on.")
    suffix = Path(body.filename).suffix.lower() or ".jpg"
    if suffix not in _IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Send a PNG, JPEG, WebP, or BMP image.")
    try:
        raw = base64.b64decode(body.data_base64.split(",", 1)[-1], validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="That image did not arrive intact.") from exc
    if not raw or len(raw) > _IMAGE_LIMIT:
        raise HTTPException(status_code=413, detail="Images must be under 10 MB.")
    folder = app_data_dir() / "captures"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"upload-{datetime.now():%Y%m%d-%H%M%S}{suffix}"
    path.write_bytes(raw)
    runtime = get_runtime()
    action = "describe" if body.action == "describe" else "ocr"
    result = VisionTool(runtime.config).execute(VisionArgs(action=action, image_path=str(path)))
    return {"ok": result.ok, "text": result.message, "file": path.name}


class DoIn(BaseModel):
    action: str
    arguments: dict = {}


@app.post("/do")
def do_command(body: DoIn) -> dict:
    from service.commands import perform

    if KILL.is_set():
        raise HTTPException(status_code=423, detail="Kill switch is on.")
    runtime = get_runtime()
    result = perform(runtime, body.action, body.arguments)
    runtime.audit("do", {"action": body.action, "ok": bool(result.get("ok"))})
    return result


@app.post("/chat/audio")
async def chat_audio(request: Request) -> dict:
    from service.phone_audio import store_speech, transcribe_upload
    from voice.kokoro_engine import synthesize

    if KILL.is_set():
        raise HTTPException(status_code=423, detail="Kill switch is on.")
    payload = await request.body()
    ok, text = transcribe_upload(payload, request.headers.get("content-type", ""))
    if not ok:
        return {"ok": False, "text": text}
    runtime = get_runtime()
    reply = runtime.assistant.handle_user_message(text, source="phone-audio", ask_on_reply=True)
    samples, rate = synthesize(reply.text or "I'm here.")
    clip = store_speech(samples, rate)
    return {"ok": True, "heard": text, "text": reply.text, "audio": f"/audio/{clip}"}


@app.get("/audio/{clip_id}")
def audio_clip(clip_id: str) -> Response:
    from service.phone_audio import take_clip

    wav = take_clip(clip_id)
    if wav is None:
        raise HTTPException(status_code=404, detail="That clip has gone.")
    return Response(content=wav, media_type="audio/wav")


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    headers = socket.headers
    if not host_allowed(headers.get("host")) or not origin_allowed(headers.get("origin"), headers.get("host")):
        await socket.close(code=4403)
        return
    runtime = get_runtime()
    local = is_local(socket.client.host if socket.client else "", headers)
    if not local and not license_gate().allows_phone:
        await socket.close(code=4402)
        return
    trusted = local or runtime.devices.valid(bearer(headers))
    await socket.accept()
    if not trusted:
        # Browsers cannot set headers on a WebSocket, so the first frame may carry the token instead.
        try:
            first = await asyncio.wait_for(socket.receive_json(), timeout=10)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await socket.close(code=4401)
            return
        if not (isinstance(first, dict) and first.get("type") == "auth" and runtime.devices.valid(str(first.get("token") or ""))):
            await socket.close(code=4401)
            return
        await socket.send_json({"type": "ready"})
    # One source per kind of client, so a 'yes' on a new socket still answers the pending question.
    source = "web" if local else "phone"
    _clients.add(socket)
    try:
        while True:
            payload = await socket.receive_json()
            if isinstance(payload, dict) and payload.get("type") == "auth":
                await socket.send_json({"type": "ready"})
                continue
            text = str(payload.get("text") or "")
            if not text or KILL.is_set():
                await socket.send_json({"type": "error", "text": "Stopped."})
                continue
            loop = asyncio.get_running_loop()

            def token(piece: str) -> None:
                asyncio.run_coroutine_threadsafe(socket.send_json({"type": "token", "text": piece}), loop)

            reply = await loop.run_in_executor(
                None,
                lambda: runtime.assistant.handle_user_message(
                    text, source=source, ask_on_reply=True, on_token=token
                ),
            )
            await socket.send_json({
                "type": "reply",
                "text": reply.text,
                "error": reply.error,
                "actions": _actions(reply),
                "confirm": bool(reply.needs_confirm),
            })
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(socket)


def _qr(data: str) -> str | None:
    try:
        import qrcode
    except ImportError:
        return None
    image = qrcode.make(data)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


from service.today import router as today_router  # noqa: E402

app.include_router(today_router)


def mount_ui(application: FastAPI) -> None:
    folder = WEB_DIST if (WEB_DIST / "index.html").exists() else WEB_PUBLIC
    if not (folder / "index.html").exists():
        return
    assets = folder / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")
    @application.get("/")
    def root() -> FileResponse:
        return FileResponse(folder / "index.html", headers={"Cache-Control": "no-cache"})

    @application.get("/{name}")
    def public_file(name: str) -> FileResponse:
        target = (folder / name).resolve()
        if target.parent != folder.resolve() or not target.is_file():
            raise HTTPException(status_code=404, detail="Not found.")
        return FileResponse(target, headers={"Cache-Control": "no-cache"})
