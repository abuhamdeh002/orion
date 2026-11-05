import { useEffect, useRef, useState } from "react";
import { Presence } from "./Presence";
import { TodayData, until } from "./Today";

type Call = <T>(path: string, init?: RequestInit) => Promise<T>;

/**
 * Ambient mode: the PC as a night-sky clock. A huge, quiet time, the constellation alive in
 * the middle, the next reminder and the weather below. Any key, click or touch brings ORION back.
 */
export function Ambient({ phase, call, onExit }: { phase: string; call: Call; onExit: () => void }) {
  const [now, setNow] = useState(Date.now());
  const [data, setData] = useState<TodayData | null>(null);
  // The page re-renders every second; a fresh onExit each time must not re-arm the listeners.
  const exit = useRef(onExit);
  exit.current = onExit;

  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    const load = () => call<TodayData>("/today").then(setData).catch(() => undefined);
    load();
    const poll = window.setInterval(load, 30000);
    const leave = () => exit.current();
    const armed = window.setTimeout(() => {
      window.addEventListener("keydown", leave, { once: true });
      window.addEventListener("pointerdown", leave, { once: true });
    }, 600);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(poll);
      window.clearTimeout(armed);
      window.removeEventListener("keydown", leave);
      window.removeEventListener("pointerdown", leave);
    };
  }, [call]);

  const date = new Date(now);
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).replace(/\s?(AM|PM)$/i, "");
  const meridiem = (date.toLocaleTimeString([], { hour: "numeric" }).match(/AM|PM/i) || [""])[0];
  const next = data?.reminders[0];
  return (
    <div className="ambient" role="dialog" aria-label="Ambient clock. Press any key to return.">
      <div className="ambient-sky">
        <Presence phase={phase} />
      </div>
      <div className="ambient-time">
        <span>{time}</span>
        {meridiem && <small>{meridiem}</small>}
      </div>
      <div className="ambient-date">{date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}</div>
      <div className="ambient-lines">
        {next && (
          <p>
            <em>Next</em> {next.title} <span>{until(next.due_at, now)}</span>
          </p>
        )}
        {data?.weather?.line && (
          <p>
            <em>Outside</em> {data.weather.line.replace(/^[^:]+:\s*/, "")}
          </p>
        )}
      </div>
      <div className="ambient-hint">Say “Hey Orion”, or press any key</div>
    </div>
  );
}
