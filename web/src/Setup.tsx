import { useEffect, useState } from "react";

type SetupStatus = {
  ready: boolean;
  backends: { local?: { ready: boolean; detail: string }; cloud?: string[]; private?: boolean };
  keys: { groq: boolean; gemini: boolean };
  links: { groq: string; gemini: string; ollama: string };
};

type Call = <T>(path: string, init?: RequestInit) => Promise<T>;

// Shown when ORION has no working model. One free key is enough to get going.
export function SetupCard({ call, onSaved }: { call: Call; onSaved: () => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [groq, setGroq] = useState("");
  const [gemini, setGemini] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    call<SetupStatus>("/setup").then(setStatus).catch(() => setStatus(null));
  }, [call]);

  async function save() {
    const body: Record<string, string> = {};
    if (groq.trim()) body.groq_api_key = groq.trim();
    if (gemini.trim()) body.gemini_api_key = gemini.trim();
    if (!Object.keys(body).length) return;
    setBusy(true);
    setError("");
    try {
      const next = await call<SetupStatus>("/setup", { method: "POST", body: JSON.stringify(body) });
      setStatus(next);
      setGroq("");
      setGemini("");
      onSaved();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  const local = status?.backends.local;
  return (
    <section className="setup-card" aria-label="Set up a model">
      <h2>Give ORION a brain</h2>
      <p>
        {local?.ready
          ? "The local model is running."
          : "Ollama isn't running on this PC."}{" "}
        {status?.backends.cloud?.length
          ? `Cloud fallback: ${status.backends.cloud.join(", ")}.`
          : "Add one free cloud key and ORION works even when Ollama is off."}
      </p>
      <div className="setup-fields">
        <label>
          <span>
            Groq key{" "}
            <a href={status?.links.groq || "https://console.groq.com/keys"} target="_blank" rel="noreferrer">get one</a>
            {status?.keys.groq && <em> saved</em>}
          </span>
          <input type="password" autoComplete="off" value={groq} onChange={(event) => setGroq(event.target.value)} placeholder="gsk_…" />
        </label>
        <label>
          <span>
            Gemini key{" "}
            <a href={status?.links.gemini || "https://aistudio.google.com/apikey"} target="_blank" rel="noreferrer">get one</a>
            {status?.keys.gemini && <em> saved</em>}
          </span>
          <input type="password" autoComplete="off" value={gemini} onChange={(event) => setGemini(event.target.value)} placeholder="AIza…" />
        </label>
      </div>
      <div className="setup-actions">
        <button type="button" onClick={save} disabled={busy || (!groq.trim() && !gemini.trim())}>
          {busy ? "Saving…" : "Save and use"}
        </button>
        <a href={status?.links.ollama || "https://ollama.com/download"} target="_blank" rel="noreferrer">
          Or install Ollama to stay fully local
        </a>
      </div>
      {error && <p className="setup-error">{error}</p>}
      <p className="setup-note">Keys are saved to this PC's .env file and are never shown again.</p>
    </section>
  );
}
