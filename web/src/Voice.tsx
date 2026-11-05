import { useEffect, useRef, useState } from "react";
import { Icon } from "./icons";

type VoiceItem = { id: string; name: string; engine: "kokoro" | "edge"; online: boolean; ready: boolean };
type Listing = { current: string; rate: number; voices: VoiceItem[] };
type Call = <T>(path: string, init?: RequestInit) => Promise<T>;

const PACES = [
  { label: "Relaxed", rate: 162 },
  { label: "Natural", rate: 180 },
  { label: "Brisk", rate: 198 },
];

/** Pick ORION's voice by ear: every voice can be previewed here before it is used. */
export function VoicePicker({ call, audio }: { call: Call; audio: (path: string) => Promise<Blob> }) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const player = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    call<Listing>("/voice/voices").then(setListing).catch(() => setNote("Voices are not available right now."));
    return () => player.current?.pause();
  }, [call]);

  const rate = listing?.rate ?? 180;

  async function preview(voice: VoiceItem) {
    player.current?.pause();
    if (playing === voice.id) {
      setPlaying(null);
      return;
    }
    setNote("");
    setLoading(voice.id);
    try {
      const blob = await audio(`/voice/sample?voice=${encodeURIComponent(voice.id)}&rate=${rate}`);
      const url = URL.createObjectURL(blob);
      const sound = new Audio(url);
      player.current = sound;
      sound.onended = () => {
        setPlaying(null);
        URL.revokeObjectURL(url);
      };
      await sound.play();
      setPlaying(voice.id);
    } catch (error) {
      setNote(error instanceof Error ? error.message : "Could not play that voice.");
    } finally {
      setLoading(null);
    }
  }

  async function choose(voice: string, pace = rate) {
    try {
      setListing(await call<Listing>("/voice/choose", { method: "POST", body: JSON.stringify({ voice, rate: pace }) }));
      setNote("");
    } catch (error) {
      setNote(error instanceof Error ? error.message : "Could not change the voice.");
    }
  }

  if (!listing) return note ? <p className="quiet">{note}</p> : <p className="quiet">Loading voices…</p>;
  const groups: [string, VoiceItem[]][] = [
    ["On this PC · private, instant", listing.voices.filter((voice) => !voice.online)],
    ["Online · Microsoft neural", listing.voices.filter((voice) => voice.online)],
  ];
  return (
    <div className="voice-picker">
      <div className="pace">
        <span>Pace</span>
        <div className="seg" role="group" aria-label="Speaking pace">
          {PACES.map((pace) => (
            <button
              key={pace.label}
              type="button"
              aria-pressed={Math.abs(rate - pace.rate) < 9}
              onClick={() => void choose(listing.current, pace.rate)}
            >
              {pace.label}
            </button>
          ))}
        </div>
      </div>
      {groups.map(([title, voices]) =>
        voices.length === 0 ? null : (
          <div key={title} className="voice-group">
            <h6>{title}</h6>
            <div className="voices">
              {voices.map((voice, index) => {
                const [name, detail] = voice.name.split(" · ");
                const inUse = listing.current === voice.id;
                return (
                  <div
                    key={voice.id}
                    className={`voice-card ${inUse ? "is-on" : ""} ${playing === voice.id ? "is-playing" : ""}`}
                    style={{ animationDelay: `${index * 0.04}s` }}
                  >
                    <button
                      type="button"
                      className="voice-play"
                      disabled={!voice.ready || loading !== null}
                      onClick={() => void preview(voice)}
                      aria-label={playing === voice.id ? `Stop ${name}` : `Preview ${name}`}
                    >
                      {loading === voice.id ? <span className="spinner" /> : playing === voice.id ? <span className="bars"><i /><i /><i /><i /></span> : <Icon name="play" />}
                    </button>
                    <div className="voice-text">
                      <b>{name}</b>
                      <span>{detail}</span>
                    </div>
                    <button type="button" className={`pill ${inUse ? "accent" : ""}`} aria-pressed={inUse} disabled={!voice.ready} onClick={() => void choose(voice.id)}>
                      {inUse ? "In use" : "Use"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ),
      )}
      {note && <p className="setup-error">{note}</p>}
    </div>
  );
}
