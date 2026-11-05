import { useCallback, useEffect, useState } from "react";
import { Icon } from "./icons";

type Reminder = { id: string; title: string; due_at: string; recurrence: string };
export type TodayData = {
  name: string | null;
  reminders: Reminder[];
  reminder_count: number;
  weather: { city: string; line: string | null } | null;
  system: { cpu?: number; memory?: number; battery?: { percent: number; charging: boolean } | null };
  memory: { count: number; latest: string | null };
  brain: string;
};
type Call = <T>(path: string, init?: RequestInit) => Promise<T>;

/** "in 42s", "in 12 min", "at 4:30 PM", "tomorrow 9:00 AM", "Fri 3:00 PM". */
export function until(dueAt: string, now: number): string {
  const due = new Date(dueAt);
  const seconds = Math.round((due.getTime() - now) / 1000);
  if (seconds <= 0) return "now";
  if (seconds < 60) return `in ${seconds}s`;
  if (seconds < 3600) return `in ${Math.round(seconds / 60)} min`;
  const clock = due.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const today = new Date(now);
  const tomorrow = new Date(now + 86400000);
  if (due.toDateString() === today.toDateString()) return `at ${clock}`;
  if (due.toDateString() === tomorrow.toDateString()) return `tomorrow ${clock}`;
  return `${due.toLocaleDateString([], { weekday: "short" })} ${clock}`;
}

/** Fills as the moment gets close: the last hour for soon reminders, the last day for later ones. */
function Countdown({ dueAt, now }: { dueAt: string; now: number }) {
  const remaining = Math.max(0, (new Date(dueAt).getTime() - now) / 1000);
  const window = remaining <= 3600 ? 3600 : 86400;
  const filled = Math.max(0.03, 1 - Math.min(1, remaining / window));
  const circumference = 2 * Math.PI * 15;
  return (
    <svg className={`countdown ${remaining < 60 ? "is-close" : ""}`} viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="15" className="countdown-track" />
      <circle cx="18" cy="18" r="15" className="countdown-fill" strokeDasharray={`${filled * circumference} ${circumference}`} />
    </svg>
  );
}

function Meter({ label, value }: { label: string; value?: number }) {
  const shown = typeof value === "number" ? value : 0;
  return (
    <div className="meter">
      <div className="meter-head">
        <span>{label}</span>
        <b>{typeof value === "number" ? `${value}%` : "—"}</b>
      </div>
      <div className="meter-bar">
        <i style={{ width: `${shown}%` }} className={shown > 85 ? "hot" : ""} />
      </div>
    </div>
  );
}

function weatherParts(line: string): { temp: string | null; words: string } {
  const temp = line.match(/(-?\d+(?:\.\d+)?)\s*°\s*C/i);
  const words = line.replace(/^[^:]+:\s*/, "").replace(/,?\s*-?\d+(?:\.\d+)?\s*°\s*C/i, "").trim();
  return { temp: temp ? `${Math.round(Number(temp[1]))}°` : null, words: words || line };
}

export function Today({
  call,
  refreshKey,
  prompts,
  onAsk,
  onFill,
  onMemory,
}: {
  call: Call;
  refreshKey: number;
  prompts: { name: string; try: string }[];
  onAsk: (text: string) => void;
  onFill: (text: string) => void;
  onMemory: () => void;
}) {
  const [data, setData] = useState<TodayData | null>(null);
  const [now, setNow] = useState(Date.now());

  const load = useCallback(() => {
    call<TodayData>("/today").then(setData).catch(() => undefined);
  }, [call]);

  useEffect(() => {
    load();
    const poll = window.setInterval(load, 15000);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, [load, refreshKey]);

  async function act(path: string, init: RequestInit) {
    await call(path, init).catch(() => undefined);
    load();
  }

  const reminders = data?.reminders ?? [];
  const weather = data?.weather;
  const parts = weather?.line ? weatherParts(weather.line) : null;
  return (
    <section className="today" aria-label="Today">
      <article className="glance glance-upcoming" style={{ animationDelay: "0.05s" }}>
        <header>
          <Icon name="bell" />
          <h4>Up next</h4>
          {data && data.reminder_count > reminders.length && <span className="glance-more">+{data.reminder_count - reminders.length} more</span>}
        </header>
        {reminders.length === 0 ? (
          <div className="glance-empty">
            <p>Nothing scheduled. Try one:</p>
            <div className="chips">
              <button type="button" onClick={() => onAsk("Remind me in 20 minutes to stretch")}>Stretch in 20 min</button>
              <button type="button" onClick={() => onAsk("Set a timer for 5 minutes")}>5-minute timer</button>
              <button type="button" onClick={() => onFill("Remind me tomorrow at 9 to ")}>Tomorrow at 9…</button>
            </div>
          </div>
        ) : (
          <ul className="upcoming">
            {reminders.slice(0, 4).map((item) => (
              <li key={item.id}>
                <Countdown dueAt={item.due_at} now={now} />
                <div className="upcoming-text">
                  <b>{item.title}</b>
                  <span>
                    {until(item.due_at, now)}
                    {item.recurrence !== "none" && ` · ${item.recurrence}`}
                  </span>
                </div>
                <div className="upcoming-actions">
                  <button type="button" title="Snooze 10 minutes" aria-label={`Snooze ${item.title}`} onClick={() => void act(`/reminders/${item.id}/snooze`, { method: "POST", body: JSON.stringify({ minutes: 10 }) })}>
                    +10
                  </button>
                  <button type="button" title="Done" aria-label={`Done with ${item.title}`} onClick={() => void act(`/reminders/${item.id}/done`, { method: "POST" })}>
                    <Icon name="check" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="glance glance-weather" style={{ animationDelay: "0.12s" }}>
        <header>
          <Icon name="sun" />
          <h4>{weather?.city || "Weather"}</h4>
        </header>
        {!weather ? (
          <div className="glance-empty">
            <p>Tell me where you are once, and the weather lives here.</p>
            <div className="chips">
              <button type="button" onClick={() => onFill("I live in ")}>Set my city</button>
            </div>
          </div>
        ) : parts ? (
          <button type="button" className="weather-now" onClick={() => onAsk("What's the weather like?")}>
            <b>{parts.temp ?? "—"}</b>
            <span>{parts.words}</span>
          </button>
        ) : (
          <div className="shimmer" aria-label="Loading the weather" />
        )}
      </article>

      <article className="glance glance-pc" style={{ animationDelay: "0.19s" }}>
        <header>
          <Icon name="chip" />
          <h4>This PC</h4>
        </header>
        <Meter label="CPU" value={data?.system.cpu} />
        <Meter label="Memory" value={data?.system.memory} />
        <p className="glance-foot">
          {data?.system.battery ? `Battery ${data.system.battery.percent}%${data.system.battery.charging ? ", charging" : ""}` : "On mains power"}
          {data?.brain && <> · {data.brain}</>}
        </p>
      </article>

      <article className="glance glance-memory" style={{ animationDelay: "0.26s" }}>
        <header>
          <Icon name="memory" />
          <h4>About you</h4>
        </header>
        <button type="button" className="memory-now" onClick={onMemory}>
          <b>{data?.memory.count ?? 0}</b>
          <span>{data?.memory.count === 1 ? "thing remembered" : "things remembered"}</span>
        </button>
        {data?.memory.latest && <p className="glance-foot quote">“{data.memory.latest}”</p>}
      </article>

      {prompts.length > 0 && (
        <div className="try-row" style={{ animationDelay: "0.33s" }}>
          <span>Try</span>
          {prompts.map((prompt) => (
            <button key={prompt.name} type="button" onClick={() => onAsk(prompt.try)}>
              {prompt.try}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
