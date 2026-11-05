import { useEffect, useRef } from "react";
import { Icon } from "./icons";
import { Presence } from "./Presence";

type Voice = { phase: string; line: string; turn: number; user: string; reply: string; awake: boolean };
type Call = <T>(path: string, init?: RequestInit) => Promise<T>;

const STATUS: Record<string, string> = {
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  confirming: "Waiting for your yes",
  idle: "Listening",
  off: "Starting the microphone",
  error: "Something's off",
};

/**
 * Full-screen voice conversation. While it's open ORION keeps listening without the wake
 * word, the constellation fills the screen and moves with the sound, and the words appear as
 * large captions: what you said, then what he says.
 */
export function VoiceMode({ voice, call, onVoice, onClose }: { voice: Voice | null; call: Call; onVoice: (voice: Voice) => void; onClose: () => void }) {
  const close = useRef(onClose);
  close.current = onClose;
  // Only this conversation: what was said before the overlay opened (an old "Time's up.") stays out.
  const opened = useRef(voice?.turn ?? 0);
  const phase = voice?.phase === "idle" || voice?.phase === "off" ? "listening" : voice?.phase || "listening";

  useEffect(() => {
    const awake = () => call<Voice>("/voice/awake", { method: "POST" }).then(onVoice).catch(() => undefined);
    awake();
    // Keep him listening for as long as the overlay is open (each awake lasts 20 s).
    const keep = window.setInterval(awake, 12000);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearInterval(keep);
      window.removeEventListener("keydown", onKey);
    };
    // onVoice is a state setter: stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call]);

  const speaking = phase === "speaking";
  const fresh = (voice?.turn ?? 0) > opened.current;
  const heard = fresh ? voice?.user || "" : "";
  const said = speaking ? voice?.line || "" : fresh ? voice?.reply || "" : "";
  return (
    <div className={`voice-mode vm-${phase}`} role="dialog" aria-label="Voice conversation">
      <div className="vm-status">
        <span className="vm-dot" />
        {STATUS[voice?.phase || "off"] || "Listening"}
      </div>
      <div className="vm-orb">
        <Presence phase={phase} />
      </div>
      <div className="vm-captions" aria-live="polite">
        {heard && <p className="vm-you" key={`you-${voice?.turn}`}>{heard}</p>}
        {said ? (
          <p className="vm-orion" key={`orion-${voice?.turn}-${speaking}`}>
            {said.split(" ").map((word, index) => (
              <span key={index} style={{ animationDelay: `${Math.min(index * 0.045, 2.4)}s` }}>
                {word}{" "}
              </span>
            ))}
          </p>
        ) : (
          <p className="vm-hint">{phase === "thinking" ? "…" : "Go ahead, I'm listening."}</p>
        )}
      </div>
      <div className="vm-controls">
        <button
          type="button"
          className="vm-button"
          onClick={() => call<Voice>("/voice/stop", { method: "POST" }).then((body) => { onVoice(body); call<Voice>("/voice/awake", { method: "POST" }).then(onVoice).catch(() => undefined); }).catch(() => undefined)}
          aria-label="Interrupt"
          title="Interrupt"
        >
          <Icon name="stop" />
          <span>Interrupt</span>
        </button>
        <button
          type="button"
          className="vm-button vm-end"
          onClick={() => {
            call<Voice>("/voice/stop", { method: "POST" }).then(onVoice).catch(() => undefined);
            onClose();
          }}
          aria-label="End voice conversation"
          title="End (Esc)"
        >
          <Icon name="cross" />
          <span>End</span>
        </button>
      </div>
    </div>
  );
}
