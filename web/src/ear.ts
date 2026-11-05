import { useCallback, useRef, useState } from "react";
import { commandAfterWake } from "./wake";

type Phase = "off" | "listening" | "speaking";

// Same token the main app saved from the pairing link, so this works from a phone too.
function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  try {
    const token = localStorage.getItem("orion-token");
    if (token) headers.Authorization = `Bearer ${token}`;
  } catch {
    /* storage blocked */
  }
  return headers;
}

export function useEar(onCommand: (text: string) => void) {
  const [phase, setPhase] = useState<Phase>("off");
  const [line, setLine] = useState("");
  const busy = useRef(false);
  const onCommandRef = useRef(onCommand);
  onCommandRef.current = onCommand;

  const speak = useCallback((text: string) => {
    if (!text.trim()) return;
    setPhase("speaking");
    fetch("/speak", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ text }),
    })
      .catch(() => undefined)
      .finally(() => setPhase("off"));
  }, []);

  async function toggle() {
    if (phase === "listening") {
      setLine("Already listening.");
      return;
    }
    if (busy.current) return;
    busy.current = true;
    setPhase("listening");
    setLine("Listening on this PC…");
    try {
      const response = await fetch("/listen", { method: "POST", headers: authHeaders() });
      const body = (await response.json()) as { ok?: boolean; text?: string; detail?: string; awake?: boolean };
      if (body.awake) {
        // The always-on microphone is already running; it is now listening without the wake word.
        setLine("I'm listening. Just talk.");
        setPhase("off");
        return;
      }
      const heard = (body.text || body.detail || "").trim();
      if (!response.ok || body.ok === false) {
        setLine(heard || "The microphone did not catch that.");
        setPhase("off");
        return;
      }
      const command = commandAfterWake(heard, true) || heard;
      setLine(heard);
      onCommandRef.current(command);
    } catch {
      setLine("The microphone service did not answer.");
      setPhase("off");
    } finally {
      busy.current = false;
    }
  }

  return { armed: phase !== "off", phase, line, missing: false, toggle, speak };
}
