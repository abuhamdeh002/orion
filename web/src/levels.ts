/**
 * Live loudness from the PC: the room through the microphone, and ORION's own voice.
 * Read by the canvases every frame; nothing re-renders. `out` is null while an online
 * voice is speaking (its audio can't be measured), and the drawing falls back to a
 * natural speech rhythm.
 */
export const live = { mic: 0, out: null as number | null, at: 0, connected: false };

let source: EventSource | null = null;

export function startLevels(hasToken: boolean): () => void {
  // EventSource can't send a token; paired phones simply don't get live levels.
  if (hasToken || !("EventSource" in window) || source) return () => undefined;
  source = new EventSource("/voice/levels");
  source.onmessage = (event) => {
    try {
      const reading = JSON.parse(String(event.data)) as { mic: number; out: number | null };
      // Rise fast, fall slowly: the way a VU meter reads to the eye.
      live.mic = reading.mic > live.mic ? reading.mic : live.mic * 0.7 + reading.mic * 0.3;
      live.out = reading.out;
      live.at = performance.now();
      live.connected = true;
    } catch {
      /* a malformed frame is skipped */
    }
  };
  source.onerror = () => {
    live.connected = false;
  };
  return () => {
    source?.close();
    source = null;
  };
}
