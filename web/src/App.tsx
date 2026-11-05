import { SetupCard } from "./Setup";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alive } from "./Alive";
import { Ambient } from "./Ambient";
import { startLevels } from "./levels";
import { Command, Palette } from "./Palette";
import { Rich } from "./Rich";
import { Today, until } from "./Today";
import { VoiceMode } from "./VoiceMode";
import { Icon } from "./icons";
import { Intro } from "./Intro";
import { Logo } from "./Logo";
import { Presence } from "./Presence";
import { Mood, Sky } from "./Sky";
import { VoicePicker } from "./Voice";

type Skill = { name: string; description: string; ready: boolean; try: string; missing?: string[] };
type Memory = { id: string; text: string; kind?: string; created_at?: string };
type Action = { tool: string; ok: boolean; message: string };
type Turn = { id: number; who: "you" | "orion"; text: string; at: string; live?: boolean; streaming?: boolean; error?: boolean; actions?: Action[]; confirm?: boolean };
type Pairing = { link?: string; reachable?: boolean; detail?: string | null; qr_png_base64: string | null; phone_link?: string; phone_qr_png_base64?: string | null };
type ChatReply = { text: string; error: boolean; actions?: Action[]; confirm?: boolean };
type Theme = "night" | "light" | "system";
type Page = "chat" | "skills" | "memory" | "settings";
type Voice = { phase: string; line: string; turn: number; user: string; reply: string; awake: boolean };
type Health = { waking?: boolean; ready: boolean; provider: string; tools: string[]; focus: boolean; killed: boolean; license?: string; license_notice?: string | null };
type Persona = { persona: string; display_name: string | null; focus_mode: boolean; calendar_ics_url: string | null };
type OrionEvent = { text: string; at: string; kind?: string; data?: { fire?: string } };

function readToken(): string {
  // Pairing links carry the token in the #fragment so it never reaches server logs.
  // Older links used ?token=; both are accepted once, saved, and then wiped from the address bar.
  const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
  const fromQuery = new URLSearchParams(window.location.search).get("token");
  const fresh = fromHash || fromQuery;
  if (fresh) {
    try { localStorage.setItem("orion-token", fresh); } catch { /* private window */ }
    window.history.replaceState(null, "", window.location.pathname);
    return fresh;
  }
  try { return localStorage.getItem("orion-token") || ""; } catch { return ""; }
}

const token = readToken();

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body as T;
}

/** Ask over /ws so the reply streams in. Falls back to /chat only if nothing was sent yet. */
function converse(text: string, onToken: (piece: string) => void): Promise<ChatReply> {
  const fallback = () => api<ChatReply>("/chat", { method: "POST", body: JSON.stringify({ text }) });
  return new Promise((resolve, reject) => {
    let socket: WebSocket;
    try {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/ws`);
    } catch {
      fallback().then(resolve, reject);
      return;
    }
    let sent = false;
    let done = false;
    socket.onopen = () => {
      if (token) socket.send(JSON.stringify({ type: "auth", token }));
      socket.send(JSON.stringify({ text }));
      sent = true;
    };
    socket.onmessage = (event) => {
      let frame: { type?: string; text?: string; error?: boolean; actions?: Action[]; confirm?: boolean };
      try {
        frame = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (frame.type === "token") {
        onToken(String(frame.text || ""));
      } else if (frame.type === "reply" || frame.type === "error") {
        done = true;
        resolve({ text: String(frame.text || ""), error: frame.type === "error" || Boolean(frame.error), actions: frame.actions, confirm: frame.confirm });
        socket.close();
      }
    };
    socket.onclose = (event) => {
      if (done) return;
      done = true;
      // Never resend once the server has the message: a tool could run twice.
      if (!sent) fallback().then(resolve, reject);
      else reject(new Error(event.code === 4401 ? "This device is not paired. Pair it again from the PC." : "The connection dropped before ORION answered."));
    };
  });
}

async function audio(path: string): Promise<Blob> {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.blob();
}

function resolveTheme(choice: Theme) {
  if (choice !== "system") return choice;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "night" : "light";
}

function stamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function greeting(name: string | null) {
  const hour = new Date().getHours();
  const part = hour < 5 ? "Still up" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}.` : `${part}.`;
}

function Typed({ text, live }: { text: string; live?: boolean }) {
  const [count, setCount] = useState(live ? 0 : text.length);
  useEffect(() => {
    if (!live) return;
    let shown = 0;
    const step = Math.max(1, Math.round(text.length / 120));
    const timer = window.setInterval(() => {
      shown += step;
      setCount(Math.min(shown, text.length));
      if (shown >= text.length) window.clearInterval(timer);
    }, 14);
    return () => window.clearInterval(timer);
  }, [text, live]);
  if (count >= text.length) return <Rich text={text} />;
  return (
    <>
      {text.slice(0, count)}
      <span className="caret" />
    </>
  );
}

function followUps(turn: Turn): string[] {
  const tools = new Set((turn.actions || []).map((action) => action.tool));
  const text = turn.text.toLowerCase();
  if (tools.has("reminders") || /remind|timer/.test(text)) return ["What reminders do I have?", "Set a timer for 5 minutes"];
  if (tools.has("weather") || /°c|degrees|forecast|rain/.test(text)) return ["What about tomorrow?", "Do I need a jacket?"];
  if (tools.has("browser")) return [];
  if (turn.text.length > 220) return ["Make it shorter", "Explain it simply", "Give me an example"];
  if (turn.text.length > 40) return ["Tell me more", "Why?"];
  return [];
}

const ACCENTS = [
  { id: "rigel", label: "Rigel", note: "blue-white" },
  { id: "betelgeuse", label: "Betelgeuse", note: "amber" },
  { id: "nebula", label: "Nebula", note: "rose and violet" },
  { id: "aurora", label: "Aurora", note: "green" },
] as const;
type Accent = (typeof ACCENTS)[number]["id"];

function UpNext({ now }: { now: number }) {
  const [items, setItems] = useState<{ id: string; title: string; due_at: string }[]>([]);
  useEffect(() => {
    const load = () => api<{ id: string; title: string; due_at: string }[]>("/reminders").then(setItems).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 15000);
    return () => window.clearInterval(timer);
  }, []);
  if (items.length === 0) return <p className="quiet">Nothing scheduled.</p>;
  return (
    <ul className="upnext">
      {items.slice(0, 4).map((item) => (
        <li key={item.id}>
          <b>{item.title}</b>
          <span>{until(item.due_at, now)}</span>
        </li>
      ))}
    </ul>
  );
}

const NAV: { id: Page; label: string; icon: "chat" | "skills" | "memory" | "settings" }[] = [
  { id: "chat", label: "Chat", icon: "chat" },
  { id: "skills", label: "Skills", icon: "skills" },
  { id: "memory", label: "Memory", icon: "memory" },
  { id: "settings", label: "Settings", icon: "settings" },
];

const PERSONAS = ["calm", "warm", "brief", "playful"];

export function App() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem("orion-theme") as Theme) || "system");
  const [intro, setIntro] = useState(() => !sessionStorage.getItem("orion-intro"));
  const [page, setPage] = useState<Page>("chat");
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillFilter, setSkillFilter] = useState<"all" | "ready" | "setup">("all");
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [persona, setPersona] = useState<Persona>({ persona: "calm", display_name: null, focus_mode: false, calendar_ics_url: null });
  const [saved, setSaved] = useState("");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [events, setEvents] = useState<OrionEvent[]>([]);
  const [toast, setToast] = useState<{ text: string; at: string } | null>(null);
  const toastSince = useRef(new Date().toISOString());
  const [clock, setClock] = useState("");
  const [started, setStarted] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [voice, setVoice] = useState<Voice | null>(null);
  const [palette, setPalette] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [killArmed, setKillArmed] = useState(false);
  const [ambient, setAmbient] = useState(false);
  const [accent, setAccent] = useState<Accent>(() => {
    try {
      return (localStorage.getItem("orion-accent") as Accent) || "rigel";
    } catch {
      return "rigel";
    }
  });
  const [idleAmbient, setIdleAmbient] = useState(() => {
    try {
      return localStorage.getItem("orion-ambient-idle") !== "off";
    } catch {
      return true;
    }
  });
  const [now, setNow] = useState(Date.now());
  const [copied, setCopied] = useState<number | null>(null);
  const [reading, setReading] = useState<number | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const seenTurn = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const stream = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const nextId = useRef(1);

  const finishIntro = useCallback(() => {
    sessionStorage.setItem("orion-intro", "1");
    setIntro(false);
  }, []);

  useEffect(() => {
    const apply = () => {
      document.documentElement.dataset.theme = resolveTheme(theme);
    };
    apply();
    localStorage.setItem("orion-theme", theme);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.accent = accent;
    try {
      localStorage.setItem("orion-accent", accent);
    } catch {
      /* private window */
    }
  }, [accent]);

  useEffect(() => startLevels(Boolean(token)), []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // After three quiet minutes the window becomes a night-sky clock (switch off in Settings).
  useEffect(() => {
    try {
      localStorage.setItem("orion-ambient-idle", idleAmbient ? "on" : "off");
    } catch {
      /* private window */
    }
    if (!idleAmbient) return;
    let last = Date.now();
    const touch = () => {
      last = Date.now();
    };
    const events = ["pointermove", "keydown", "pointerdown", "wheel"];
    events.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    const timer = window.setInterval(() => {
      const quiet = document.documentElement.dataset.phase === "idle";
      if (quiet && Date.now() - last > 180000 && document.visibilityState === "visible") setAmbient(true);
    }, 5000);
    return () => {
      events.forEach((name) => window.removeEventListener(name, touch));
      window.clearInterval(timer);
    };
  }, [idleAmbient]);

  const refreshHealth = useCallback(() => {
    api<Health>("/health")
      .then((body) => {
        setHealth(body);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    tick();
    const clockTimer = window.setInterval(tick, 1000);
    refreshHealth();
    api<Skill[]>("/skills").then(setSkills).catch(() => setSkills([]));
    api<Persona>("/persona").then(setPersona).catch(() => undefined);
    const loadEvents = () => api<OrionEvent[]>("/events").then(setEvents).catch(() => undefined);
    loadEvents();
    // On the PC, hear about reminders the moment they fire. Phones (with a token) keep polling.
    let stream: EventSource | null = null;
    if (!token && "EventSource" in window) {
      stream = new EventSource("/events/stream");
      stream.addEventListener("reminder", loadEvents);
    }
    const pollTimer = window.setInterval(() => {
      refreshHealth();
      loadEvents();
    }, 15000);
    const closeStream = () => stream?.close();
    window.addEventListener("beforeunload", closeStream);
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    const pullVoice = () =>
      api<Voice>("/voice")
        .then((body) => {
          setVoice(body);
          if (body.turn > seenTurn.current && body.user) {
            seenTurn.current = body.turn;
            const at = stamp();
            setTurns((current) => [
              ...current,
              { id: nextId.current++, who: "you", text: body.user, at },
              { id: nextId.current++, who: "orion", text: body.reply, at, live: true },
            ]);
          }
        })
        .catch(() => undefined);
    pullVoice();
    const voiceTimer = window.setInterval(pullVoice, 800);
    return () => {
      window.clearInterval(clockTimer);
      window.clearInterval(pollTimer);
      window.clearInterval(voiceTimer);
    };
  }, [refreshHealth]);

  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [busy, started]);

  useEffect(() => {
    const node = stream.current;
    if (!node || !follow.current) return;
    node.scrollTop = node.scrollHeight;
  }, [turns, busy, page]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement;
      if (event.key === "Escape") {
        if (typing) {
          (document.activeElement as HTMLElement).blur();
          return;
        }
        api<Voice>("/voice/stop", { method: "POST" }).then(setVoice).catch(() => undefined);
        return;
      }
      if (event.key.toLowerCase() === "k" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        setPalette((open) => !open);
        return;
      }
      if (event.key === "/" && !typing) {
        event.preventDefault();
        setPage("chat");
        window.setTimeout(() => input.current?.focus(), 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const waking = Boolean(health && !health.ready && health.waking && !health.killed);
  const phase = waking
    ? "linking"
    : offline || health?.killed || (health && !health.ready)
    ? "error"
    : busy || voice?.phase === "thinking"
      ? "thinking"
      : voice?.phase === "speaking"
        ? "speaking"
        : voice?.phase === "listening" || voice?.awake
          ? "listening"
          : health
            ? "idle"
            : "linking";
  useEffect(() => {
    document.documentElement.dataset.phase = phase;
  }, [phase]);

  useEffect(() => {
    const fresh = events.filter((item) => item.kind === "reminder" && item.data?.fire === "fired" && item.at > toastSince.current);
    if (fresh.length === 0) return;
    const latest = fresh[fresh.length - 1];
    toastSince.current = latest.at;
    setToast({ text: latest.text, at: latest.at });
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        new Notification("ORION", { body: latest.text, icon: "/favicon.svg", tag: `orion-${latest.at}` });
      } catch {
        /* some browsers only allow notifications from a service worker */
      }
    }
    const timer = window.setTimeout(() => setToast(null), 20000);
    return () => window.clearTimeout(timer);
  }, [events]);

  const statusText = phase === "error"
    ? offline
      ? "service offline"
      : health?.killed
        ? "agent stopped"
        : "model offline"
    : phase === "linking"
      ? waking ? "waking up" : "linking"
      : phase;
  const mood: Mood = phase === "error" ? "error" : phase === "idle" || phase === "linking" ? "idle" : "thinking";

  const providerRows = useMemo(() => {
    const raw = health?.provider || "";
    const [model, ...rest] = raw.split(";").map((part) => part.trim());
    const extra = Object.fromEntries(rest.map((part) => part.split("=") as [string, string]));
    const shown = health?.waking && !health.ready ? "waking up" : !health?.ready ? "not running" : model;
    return { model: shown || "unknown", cloud: extra.cloud || "none", mode: extra.mode || "local" };
  }, [health]);

  function fill(textToType: string) {
    setPage("chat");
    setText(textToType);
    window.setTimeout(() => {
      input.current?.focus();
      const end = textToType.length;
      input.current?.setSelectionRange(end, end);
    }, 0);
  }

  async function copyTurn(turn: Turn) {
    try {
      await navigator.clipboard.writeText(turn.text);
      setCopied(turn.id);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      /* clipboard blocked */
    }
  }

  async function readAloud(turn: Turn) {
    player.current?.pause();
    if (reading === turn.id) {
      setReading(null);
      return;
    }
    setReading(turn.id);
    try {
      const headers = new Headers({ "Content-Type": "application/json" });
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch("/voice/say", { method: "POST", headers, body: JSON.stringify({ text: turn.text }) });
      if (!response.ok) throw new Error("no audio");
      const url = URL.createObjectURL(await response.blob());
      const sound = new Audio(url);
      player.current = sound;
      sound.onended = () => {
        setReading(null);
        URL.revokeObjectURL(url);
      };
      await sound.play();
    } catch {
      setReading(null);
    }
  }

  const commands: Command[] = [
    { id: "voice-mode", label: "Voice conversation", hint: "talk speak hands free live", icon: "wave", group: "Voice", run: () => setVoiceMode(true) },
    { id: "new", label: "New chat", hint: "clear start over fresh", icon: "compose", group: "Chat", run: () => setTurns([]) },
    { id: "talk", label: "Talk to ORION", hint: "listen microphone voice", icon: "mic", group: "Voice", run: () => void api("/voice/awake", { method: "POST" }).then((body) => setVoice(body as Voice)).catch(() => undefined) },
    { id: "hush", label: "Stop talking", hint: "quiet silence hush", icon: "stop", group: "Voice", run: () => void api("/voice/stop", { method: "POST" }).then((body) => setVoice(body as Voice)).catch(() => undefined) },
    { id: "timer5", label: "Set a timer for 5 minutes", hint: "countdown", icon: "bell", group: "Do", run: () => void ask("Set a timer for 5 minutes") },
    { id: "remind", label: "Remind me…", hint: "reminder later tomorrow", icon: "bell", group: "Do", run: () => fill("Remind me in 30 minutes to ") },
    { id: "list", label: "What's on my reminders?", hint: "upcoming list", icon: "bell", group: "Do", run: () => void ask("What reminders do I have?") },
    { id: "weather", label: "What's the weather?", hint: "forecast outside temperature", icon: "sun", group: "Do", run: () => void ask("What's the weather like?") },
    { id: "search", label: "Search the web for…", hint: "google look up", icon: "search", group: "Do", run: () => fill("Search the web for ") },
    { id: "calc", label: "Open Calculator", hint: "app launch", icon: "sparkle", group: "Do", run: () => void ask("Open calculator") },
    { id: "music", label: "Pause or play music", hint: "spotify media", icon: "play", group: "Do", run: () => void ask("Pause the music") },
    { id: "ambient", label: "Ambient clock", hint: "screensaver night sky time", icon: "moon", group: "View", run: () => setAmbient(true) },
    { id: "chat", label: "Go to Chat", icon: "chat", group: "Go", run: () => setPage("chat") },
    { id: "skills", label: "Go to Skills", icon: "skills", group: "Go", run: () => setPage("skills") },
    { id: "memory", label: "Go to Memory", hint: "remembered facts", icon: "memory", group: "Go", run: () => openMemory() },
    { id: "settings", label: "Go to Settings", hint: "preferences voice", icon: "settings", group: "Go", run: () => setPage("settings") },
    { id: "voice", label: "Choose a voice", hint: "speech tts accent", icon: "speaker", group: "Go", run: () => setPage("settings") },
    ...(["night", "light", "system"] as Theme[]).map((choice) => ({ id: `theme-${choice}`, label: `Theme: ${choice}`, hint: "dark mode appearance", icon: "moon" as const, group: "Look", run: () => setTheme(choice) })),
    ...ACCENTS.map((choice) => ({ id: `accent-${choice.id}`, label: `Accent: ${choice.label}`, hint: `colour color ${choice.note}`, icon: "swatch" as const, group: "Look", run: () => setAccent(choice.id) })),
    { id: "kill", label: health?.killed ? "Resume the agent" : "Stop the agent (kill switch)", hint: "off disable", icon: health?.killed ? "play" : "stop", group: "Safety", run: () => void toggleKill() },
  ];

  async function ask(said: string) {
    const clean = said.trim();
    if (!clean || busy) return;
    if (/\b(?:remind|reminder|timer|alarm|wake me|beep)\b/i.test(clean) && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => undefined);
    }
    setPage("chat");
    setText("");
    setBusy(true);
    setStarted(Date.now());
    setElapsed(0);
    setTurns((current) => [...current, { id: nextId.current++, who: "you", text: clean, at: stamp() }]);
    const id = nextId.current++;
    let streamed = "";
    try {
      const body = await converse(clean, (piece) => {
        streamed += piece;
        const shown = streamed;
        setTurns((current) =>
          current.some((turn) => turn.id === id)
            ? current.map((turn) => (turn.id === id ? { ...turn, text: shown } : turn))
            : [...current, { id, who: "orion", text: shown, at: stamp(), streaming: true }],
        );
      });
      const final: Turn = {
        id, who: "orion", text: body.text || "No reply.", at: stamp(),
        live: !streamed, error: body.error, actions: body.actions, confirm: body.confirm,
      };
      setTurns((current) =>
        current.some((turn) => turn.id === id)
          ? current.map((turn) => (turn.id === id ? { ...final, at: turn.at } : turn))
          : [...current, final],
      );
    } catch (error) {
      setTurns((current) => [
        ...current.map((turn) => (turn.id === id ? { ...turn, streaming: false } : turn)),
        { id: nextId.current++, who: "orion", text: error instanceof Error ? error.message : "The service did not answer.", at: stamp(), error: true },
      ]);
    } finally {
      setBusy(false);
      refreshHealth();
    }
  }

  async function sendImage(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      setTurns((current) => [...current, { id: nextId.current++, who: "orion", text: "Images must be under 10 MB.", at: stamp(), error: true }]);
      return;
    }
    const data = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    setTurns((current) => [...current, { id: nextId.current++, who: "you", text: `Image: ${file.name}`, at: stamp() }]);
    setBusy(true);
    try {
      const body = await api<{ ok: boolean; text: string }>("/image", {
        method: "POST",
        body: JSON.stringify({ data_base64: data, filename: file.name }),
      });
      setTurns((current) => [...current, { id: nextId.current++, who: "orion", text: body.text || "No text found.", at: stamp(), error: !body.ok }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "The image could not be read.";
      setTurns((current) => [...current, { id: nextId.current++, who: "orion", text: message, at: stamp(), error: true }]);
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(text);
  }

  useEffect(() => {
    const box = input.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 168)}px`;
  }, [text]);

  async function openMemory() {
    setPage("memory");
    setMemories(await api<Memory[]>("/memory").catch(() => []));
  }

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryDraft.trim()) return;
    await api("/memory", { method: "POST", body: JSON.stringify({ text: memoryDraft }) }).catch(() => undefined);
    setMemoryDraft("");
    await openMemory();
  }

  async function forget(id: string) {
    await api(`/memory/${id}`, { method: "DELETE" }).catch(() => undefined);
    setMemories((current) => current.filter((item) => item.id !== id));
  }

  async function savePersona(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/persona", {
        method: "POST",
        body: JSON.stringify({
          persona: persona.persona,
          display_name: persona.display_name || "",
          focus_mode: persona.focus_mode,
          calendar_ics_url: persona.calendar_ics_url || "",
        }),
      });
      setSaved("Saved.");
    } catch (error) {
      setSaved(error instanceof Error ? error.message : "Could not save.");
    }
    window.setTimeout(() => setSaved(""), 2400);
  }

  async function pair() {
    try {
      setPairing(await api<Pairing>("/pair", { method: "POST", body: JSON.stringify({ name: "phone" }) }));
    } catch (error) {
      setSaved(error instanceof Error ? error.message : "Pairing failed.");
    }
  }

  async function toggleKill() {
    await api(health?.killed ? "/resume" : "/kill", { method: "POST" }).catch(() => undefined);
    setKillArmed(false);
    refreshHealth();
  }

  // Stopping ORION takes two taps: one tap was too easy to do by accident.
  function onKillButton() {
    if (health?.killed || killArmed) {
      void toggleKill();
      return;
    }
    setKillArmed(true);
    window.setTimeout(() => setKillArmed(false), 3000);
  }

  const shownSkills = skills.filter((skill) => (skillFilter === "all" ? true : skillFilter === "ready" ? skill.ready : !skill.ready));
  const shownMemories = memories.filter((item) => item.text.toLowerCase().includes(memoryQuery.toLowerCase()));
  const suggestions = skills.filter((skill) => skill.ready && skill.try).slice(0, 3);
  const prompts = suggestions.length > 0 ? suggestions.map((skill) => ({ name: skill.name, try: skill.try })) : [
    { name: "Time", try: "what time is it" },
    { name: "Weather", try: "what's the weather" },
    { name: "Calculator", try: "open calculator" },
  ];

  return (
    <>
      <div className="backdrop" />
      <Sky mood={mood} />
      <div className="grain" />
      {intro && <Intro onDone={finishIntro} />}
      {palette && <Palette commands={commands} onAsk={(said) => void ask(said)} onClose={() => setPalette(false)} />}
      {ambient && <Ambient phase={phase} call={api} onExit={() => setAmbient(false)} />}
      {voiceMode && <VoiceMode voice={voice} call={api} onVoice={setVoice} onClose={() => setVoiceMode(false)} />}
      <div className={`edge-glow eg-${voiceMode && phase === "idle" ? "listening" : phase}`} aria-hidden="true" />
      {toast && (
        <div className="toast" role="alert" key={toast.at}>
          <span className="toast-bell" aria-hidden="true">
            <Icon name="bell" />
          </span>
          <div className="toast-text">
            <b>{toast.text === "Timer" ? "Time's up" : "Reminder"}</b>
            {toast.text !== "Timer" && <span>{toast.text}</span>}
          </div>
          <button type="button" className="pill" onClick={() => setToast(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className={`frame ${intro ? "is-hidden" : "is-in"}`}>
        <nav className="rail panel">
          <div className="brand" title="ORION">
            <Logo size={34} />
          </div>
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className="rail-button"
              data-label={item.label}
              aria-label={item.label}
              aria-current={page === item.id ? "page" : undefined}
              onClick={() => (item.id === "memory" ? openMemory() : setPage(item.id))}
            >
              <Icon name={item.icon} />
              <small>{item.label}</small>
            </button>
          ))}
          <div className="spacer" />
          <button type="button" className="rail-button" data-label="Ambient clock" aria-label="Ambient clock" onClick={() => setAmbient(true)}>
            <Icon name="moon" />
            <small>Ambient</small>
          </button>
          <button
            type="button"
            className={`rail-button kill ${health?.killed ? "is-killed" : ""} ${killArmed ? "is-armed" : ""}`}
            data-label={health?.killed ? "Resume agent" : "Stop agent"}
            aria-label={health?.killed ? "Resume ORION" : killArmed ? "Tap again to stop ORION" : "Stop ORION"}
            onClick={onKillButton}
          >
            <Icon name={health?.killed ? "play" : "stop"} />
            <small>{health?.killed ? "Resume" : killArmed ? "Tap again" : "Stop"}</small>
          </button>
        </nav>

        <main className="main panel">
          <header className="bar">
            <div className="bar-title">
              <span className="wordmark">ORION</span>
              <span className="crumb">/ {NAV.find((item) => item.id === page)?.label}</span>
            </div>
            {turns.length > 0 && page === "chat" && (
              <button type="button" className="icon-pill" onClick={() => setTurns([])} aria-label="New chat" title="New chat">
                <Icon name="compose" />
              </button>
            )}
            <button type="button" className="ask-pill" onClick={() => setPalette(true)} aria-label="Search or ask (Ctrl+K)">
              <Icon name="search" />
              <span>Search or ask</span>
              <kbd>Ctrl K</kbd>
            </button>
            <div className={`status-chip mood-${mood}`}>
              <i className="pip" />
              {statusText}
              {busy && <span className="elapsed">{elapsed}s</span>}
            </div>
            <div className="bar-right">
              <span className="clock">{clock}</span>
              <div className="seg" role="group" aria-label="Theme">
                {(["night", "light", "system"] as Theme[]).map((choice) => (
                  <button key={choice} type="button" aria-pressed={theme === choice} onClick={() => setTheme(choice)}>
                    {choice}
                  </button>
                ))}
              </div>
            </div>
          </header>

          {page === "chat" && (
            <>
              <div className={`content deck page-in ${turns.length > 0 ? "has-log" : ""}`}>
                {turns.length === 0 && (
                  <>
                    <section className="stage">
                      <div className="instrument">
                        <Presence phase={phase} />
                      </div>
                      <div className="stage-copy">
                        <Alive text={greeting(persona.display_name)} />
                        <p className="lede">
                          {health?.killed
                            ? "ORION is switched off: no voice, no actions, nothing on your phone."
                            : offline
                              ? "The ORION service is not answering."
                              : waking
                                ? "Give me a moment to wake up."
                                : health && !health.ready
                                ? "No model is running yet. Set one up below."
                                : "Say Hey Orion, or type below."}
                        </p>
                      </div>
                    </section>
                    {health?.killed && (
                      <div className="stopped-note" role="status">
                        <span>The kill switch is on.</span>
                        <button type="button" className="pill accent" onClick={() => void toggleKill()}>
                          <Icon name="play" /> Turn ORION back on
                        </button>
                      </div>
                    )}
                    {waking && (
                      <p className="waking-note" role="status">
                        <span className="belt" aria-hidden="true"><i /><i /><i /></span>
                        Waking the brain. Reminders, timers, apps and the time already work.
                      </p>
                    )}
                    {health && !health.ready && !health.waking && !health.killed && !offline && <SetupCard call={api} onSaved={refreshHealth} />}
                    {health?.license_notice && <p className="license-note" role="status">{health.license_notice}</p>}
                    <Today
                      call={api}
                      refreshKey={events.length}
                      prompts={prompts}
                      onAsk={(said) => void ask(said)}
                      onFill={fill}
                      onMemory={() => openMemory()}
                    />
                  </>
                )}
                <div
                  className="stream"
                  ref={stream}
                  onScroll={(event) => {
                    const node = event.currentTarget;
                    follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 64;
                  }}
                >
                  <div className="stream-anchor" />
                  {turns.map((turn) => (
                    <article key={turn.id} className={`msg ${turn.who} ${turn.error ? "is-error" : ""}`}>
                      <div className="meta">
                        {turn.who === "you" ? "you" : "orion"} · {turn.at}
                      </div>
                      <div className="body">
                        {turn.who !== "orion" ? turn.text : turn.streaming ? <>{turn.text}<span className="caret" /></> : <Typed text={turn.text} live={turn.live} />}
                      </div>
                      {turn.who === "orion" && !turn.streaming && !turn.error && turn.text.length > 0 && (
                        <div className="msg-actions">
                          <button type="button" onClick={() => void copyTurn(turn)} aria-label="Copy reply">
                            <Icon name={copied === turn.id ? "check" : "copy"} />
                            {copied === turn.id ? "Copied" : "Copy"}
                          </button>
                          <button type="button" className={reading === turn.id ? "is-on" : ""} onClick={() => void readAloud(turn)} aria-label="Read reply aloud">
                            <Icon name={reading === turn.id ? "stop" : "speaker"} />
                            {reading === turn.id ? "Stop" : "Read aloud"}
                          </button>
                        </div>
                      )}
                      {turn.who === "orion" && !busy && !turn.streaming && turn.id === turns[turns.length - 1]?.id && followUps(turn).length > 0 && (
                        <div className="follow-ups">
                          {followUps(turn).map((prompt) => (
                            <button key={prompt} type="button" onClick={() => void ask(prompt)}>
                              {prompt}
                            </button>
                          ))}
                        </div>
                      )}
                      {turn.confirm && (
                        <div className="confirm">
                          <button type="button" className="pill accent" onClick={() => void ask("yes")}>Yes</button>
                          <button type="button" className="pill" onClick={() => void ask("no")}>No</button>
                        </div>
                      )}
                      {turn.actions && turn.actions.length > 0 && (
                        <ol className="timeline">
                          {turn.actions.map((action, index) => (
                            <li key={index} className={action.ok ? "ok" : "fail"}>
                              <Icon name={action.ok ? "check" : "cross"} />
                              <b>{action.tool}</b>
                              <span>{action.message}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </article>
                  ))}
                  {busy && !turns.some((turn) => turn.streaming) && (
                    <div className="thinking">
                      <span className="belt" aria-hidden="true">
                        <i />
                        <i />
                        <i />
                      </span>
                      <span className="shimmer-text">Thinking</span>
                      {elapsed > 1 && <span className="elapsed">{elapsed}s</span>}
                    </div>
                  )}
                </div>
              </div>
              <form className="composer-wrap" onSubmit={submit}>
                <div className={`ear ${voice?.phase === "listening" || voice?.awake ? "listening" : ""} ${voice?.phase === "speaking" ? "speaking" : ""}`}>
                  <button
                    type="button"
                    className="mic"
                    aria-pressed={Boolean(voice?.awake)}
                    onClick={() => api("/voice/awake", { method: "POST" }).then((body) => setVoice(body as Voice)).catch(() => undefined)}
                    aria-label="Talk to Orion"
                    title="Listen once"
                  >
                    <Icon name="mic" />
                  </button>
                  <button
                    type="button"
                    className="halt"
                    onClick={() => api("/voice/stop", { method: "POST" }).then((body) => setVoice(body as Voice)).catch(() => undefined)}
                    aria-label="Stop Orion"
                  >
                    <Icon name="stop" />
                  </button>
                  <span>{phase === "error" ? statusText : voice?.line || "Say Hey Orion. Press Stop, or Escape, to shut him up."}</span>
                </div>
                <div className="composer">
                  <textarea
                    ref={input}
                    rows={1}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        void ask(text);
                      }
                    }}
                    placeholder={busy ? "ORION is working…" : "Ask ORION anything"}
                    aria-label="Message ORION"
                  />
                  <kbd>/</kbd>
                  <label className="attach" aria-label="Read a photo or image" title="Read a photo or image">
                    <Icon name="image" />
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp,image/bmp"
                      capture="environment"
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        event.target.value = "";
                        if (file) void sendImage(file);
                      }}
                    />
                  </label>
                  {text.trim() ? (
                    <button className="send" type="submit" disabled={busy} aria-label="Send">
                      <Icon name="send" />
                    </button>
                  ) : (
                    <button className="send voice-go" type="button" onClick={() => setVoiceMode(true)} aria-label="Start a voice conversation" title="Voice conversation">
                      <Icon name="wave" />
                    </button>
                  )}
                </div>
              </form>
            </>
          )}

          {page === "skills" && (
            <div className="content pad page-in" key="skills">
              <div className="page-head">
                <div>
                  <Alive tag="h3" text="Everything ORION can do" />
                  <p className="lede small">
                    {skills.filter((skill) => skill.ready).length} of {skills.length} skills ready
                  </p>
                </div>
                <div className="seg" role="group" aria-label="Filter skills">
                  {(["all", "ready", "setup"] as const).map((choice) => (
                    <button key={choice} type="button" aria-pressed={skillFilter === choice} onClick={() => setSkillFilter(choice)}>
                      {choice === "setup" ? "needs setup" : choice}
                    </button>
                  ))}
                </div>
              </div>
              {shownSkills.length === 0 && <p className="quiet">No skills in this filter.</p>}
              <div className="grid">
                {shownSkills.map((skill, index) => (
                  <article key={skill.name} className="card" style={{ animationDelay: `${index * 0.03}s` }}>
                    <div className="card-top">
                      <b>{skill.name}</b>
                      <span className={`tag ${skill.ready ? "ready" : "setup"}`}>{skill.ready ? "ready" : "setup"}</span>
                    </div>
                    <p>{skill.description}</p>
                    {!skill.ready && skill.missing && skill.missing.length > 0 && <p className="missing">Missing: {skill.missing.join(", ")}</p>}
                    {skill.ready && skill.try && (
                      <button type="button" className="try" onClick={() => ask(skill.try)}>
                        “{skill.try}”
                      </button>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}

          {page === "memory" && (
            <div className="content pad page-in" key="memory">
              <div className="page-head">
                <div>
                  <Alive tag="h3" text="What ORION remembers" />
                  <p className="lede small">Nothing is stored without showing up here. Forget anything.</p>
                </div>
                <input className="search" value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} placeholder="Search memory" />
              </div>
              <form className="add-row" onSubmit={addMemory}>
                <input value={memoryDraft} onChange={(event) => setMemoryDraft(event.target.value)} placeholder="Add a fact, e.g. I prefer Celsius" />
                <button type="submit" className="pill accent">
                  <Icon name="plus" /> Remember
                </button>
              </form>
              {shownMemories.length === 0 ? (
                <div className="empty">
                  <Logo size={56} spin={false} />
                  <p>{memories.length === 0 ? "No memories yet." : "No memory matches that search."}</p>
                </div>
              ) : (
                <ul className="memory-list">
                  {shownMemories.map((item) => (
                    <li key={item.id}>
                      <span className="kind">{item.kind || "fact"}</span>
                      <p>{item.text}</p>
                      <button type="button" className="pill" onClick={() => forget(item.id)}>
                        Forget
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {page === "settings" && (
            <form className="content pad settings page-in" onSubmit={savePersona}>
              <section>
                <h4>Voice</h4>
                <p className="lede small">Right now: {statusText}. Say Hey Orion, or use the mic. Escape stops him when you are not typing. Press play to hear a voice before choosing it.</p>
                <VoicePicker call={api} audio={audio} />
              </section>
              <section>
                <h4>Appearance</h4>
                <div className="themes">
                  {(["night", "light", "system"] as Theme[]).map((choice) => (
                    <button key={choice} type="button" className={`theme-card t-${choice}`} aria-pressed={theme === choice} onClick={() => setTheme(choice)}>
                      <span className="swatch" />
                      {choice}
                    </button>
                  ))}
                </div>
              </section>
              <section>
                <h4>Accent</h4>
                <div className="accents">
                  {ACCENTS.map((choice) => (
                    <button key={choice.id} type="button" className={`accent-card a-${choice.id}`} aria-pressed={accent === choice.id} onClick={() => setAccent(choice.id)}>
                      <span className="accent-dot" />
                      <b>{choice.label}</b>
                      <small>{choice.note}</small>
                    </button>
                  ))}
                </div>
                <label className="toggle">
                  <input type="checkbox" checked={idleAmbient} onChange={(event) => setIdleAmbient(event.target.checked)} />
                  <span className="track" />
                  Become an ambient night-sky clock after three quiet minutes
                </label>
              </section>
              <section>
                <h4>Identity</h4>
                <label>
                  Your name
                  <input
                    value={persona.display_name || ""}
                    onChange={(event) => setPersona({ ...persona, display_name: event.target.value })}
                    placeholder="How ORION should address you"
                  />
                </label>
                <label>
                  Persona
                  <div className="seg wide">
                    {PERSONAS.map((choice) => (
                      <button key={choice} type="button" aria-pressed={persona.persona === choice} onClick={() => setPersona({ ...persona, persona: choice })}>
                        {choice}
                      </button>
                    ))}
                  </div>
                </label>
              </section>
              <section>
                <h4>Ambient</h4>
                <label className="toggle">
                  <input type="checkbox" checked={persona.focus_mode} onChange={(event) => setPersona({ ...persona, focus_mode: event.target.checked })} />
                  <span className="track" />
                  Focus mode mutes briefings and nudges
                </label>
                <label>
                  Calendar ICS link
                  <input
                    value={persona.calendar_ics_url || ""}
                    onChange={(event) => setPersona({ ...persona, calendar_ics_url: event.target.value })}
                    placeholder="Secret ICS address from Google or Outlook"
                  />
                </label>
              </section>
              <section>
                <h4>Phone</h4>
                <p className="lede small">Pair from this PC, then open the link on your phone over Tailscale HTTPS. Install it to the home screen.</p>
                <button type="button" className="pill accent" onClick={pair}>
                  Pair a phone
                </button>
                {pairing && pairing.reachable !== false && (
                  <div className="pairing">
                    {pairing.qr_png_base64 && <img src={`data:image/png;base64,${pairing.qr_png_base64}`} alt="Pairing QR code" />}
                    <code>{pairing.link}</code>
                  </div>
                )}
                {pairing && pairing.phone_link && (
                  <div className="pairing">
                    {pairing.phone_qr_png_base64 && <img src={`data:image/png;base64,${pairing.phone_qr_png_base64}`} alt="Android app pairing QR code" />}
                    <span className="small">Scan this one with the ORION Android app to connect through the cloud relay.</span>
                  </div>
                )}
                {pairing && pairing.reachable === false && !pairing.phone_link && <p className="pair-note">{pairing.detail}</p>}
              </section>
              <div className="save-row">
                <button type="submit" className="pill accent">
                  Save settings
                </button>
                <span className="saved">{saved}</span>
              </div>
            </form>
          )}
        </main>

        <aside className="telemetry panel">
          <div className="gauges" aria-hidden="true">
            <div className="gauge" style={{ ["--p" as string]: `${Math.min(100, (health?.tools.length ?? 0) * 8)}%` }}>
              <b>{health?.tools.length ?? 0}</b>
              <span>tools</span>
            </div>
            <div className={`gauge phase-${phase}`} style={{ ["--p" as string]: phase === "speaking" ? "100%" : phase === "listening" ? "72%" : phase === "thinking" ? "86%" : phase === "error" ? "18%" : "28%" }}>
              <b>{statusText}</b>
              <span>voice</span>
            </div>
          </div>
          <section className="tile">
            <h5>Up next</h5>
            <UpNext now={now} />
          </section>
          <section className="tile">
            <h5>Link</h5>
            <dl>
              <div>
                <dt>model</dt>
                <dd>{providerRows.model}</dd>
              </div>
              <div>
                <dt>cloud</dt>
                <dd>{providerRows.cloud}</dd>
              </div>
              <div>
                <dt>mode</dt>
                <dd>{providerRows.mode}</dd>
              </div>
              <div>
                <dt>tools</dt>
                <dd>{health?.tools.length ?? 0}</dd>
              </div>
              <div>
                <dt>agent</dt>
                <dd className={health?.killed ? "warn" : ""}>{health?.killed ? "stopped" : "armed"}</dd>
              </div>
            </dl>
          </section>
          <section className="tile grow">
            <h5>Signals</h5>
            {events.length === 0 ? (
              <p className="quiet">No signals yet. Reminders, briefings, and watches land here.</p>
            ) : (
              <ul className="events">
                {[...events].reverse().slice(0, 6).map((item, index) => (
                  <li key={`${item.at}-${index}`}>
                    <time>{new Date(item.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
                    {item.kind && <em>{item.kind}</em>}
                    {item.text}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="tile keys">
            <h5>Keys</h5>
            <p>
              <kbd>/</kbd> focus · <kbd>Win</kbd>+<kbd>Alt</kbd>+<kbd>Space</kbd> open · <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Esc</kbd> stop
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
