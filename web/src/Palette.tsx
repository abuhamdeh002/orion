import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, IconName } from "./icons";

export type Command = { id: string; label: string; hint?: string; icon: IconName; group: string; run: () => void };

/** Letters in order, not necessarily together: "tmr" finds "Set a timer". Earlier, tighter matches win. */
function score(query: string, label: string): number {
  if (!query) return 1;
  const text = label.toLowerCase();
  const wanted = query.toLowerCase().trim();
  if (text.includes(wanted)) return 100 - text.indexOf(wanted);
  let at = -1;
  let gaps = 0;
  for (const char of wanted) {
    const found = text.indexOf(char, at + 1);
    if (found < 0) return 0;
    gaps += found - at - 1;
    at = found;
  }
  return Math.max(1, 50 - gaps);
}

/** Ctrl+K: every action, page and common request in one place. Typing anything else asks ORION. */
export function Palette({ commands, onAsk, onClose }: { commands: Command[]; onAsk: (text: string) => void; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => field.current?.focus(), []);

  const shown = useMemo(() => {
    const ranked = commands
      .map((command) => ({ command, rank: Math.max(score(query, command.label), score(query, command.hint || "") * 0.6) }))
      .filter((item) => item.rank > 0)
      .sort((a, b) => b.rank - a.rank)
      .map((item) => item.command);
    const ask: Command[] = query.trim()
      ? [{ id: "ask", label: `Ask ORION: “${query.trim()}”`, icon: "send", group: "Ask", run: () => onAsk(query.trim()) }]
      : [];
    return [...(ranked.length && score(query, ranked[0].label) >= 30 ? [] : ask), ...ranked.slice(0, 9), ...(ranked.length && score(query, ranked[0].label) >= 30 ? ask : [])];
  }, [commands, query, onAsk]);

  useEffect(() => setIndex(0), [query]);

  function run(command: Command | undefined) {
    if (!command) return;
    onClose();
    command.run();
  }

  return (
    <div className="palette-veil" onMouseDown={onClose} role="presentation">
      <div className="palette" role="dialog" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()}>
        <div className="palette-search">
          <Icon name="search" />
          <input
            ref={field}
            value={query}
            placeholder="Do something, go somewhere, or just ask…"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setIndex((current) => Math.min(shown.length - 1, current + 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setIndex((current) => Math.max(0, current - 1));
              } else if (event.key === "Enter") {
                event.preventDefault();
                run(shown[index]);
              } else if (event.key === "Escape") {
                event.preventDefault();
                onClose();
              }
            }}
            aria-label="Search commands"
          />
          <kbd>Esc</kbd>
        </div>
        <ul className="palette-list" role="listbox">
          {shown.map((command, row) => (
            <li
              key={command.id}
              role="option"
              aria-selected={row === index}
              className={row === index ? "is-on" : ""}
              onMouseEnter={() => setIndex(row)}
              onClick={() => run(command)}
              style={{ animationDelay: `${row * 0.02}s` }}
            >
              <span className="palette-icon">
                <Icon name={command.icon} />
              </span>
              <span className="palette-label">{command.label}</span>
              <span className="palette-group">{command.group}</span>
            </li>
          ))}
          {shown.length === 0 && <li className="palette-none">Nothing matches. Press Enter to ask ORION.</li>}
        </ul>
        <footer className="palette-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span><kbd>Enter</kbd> run</span>
          <span><kbd>Ctrl</kbd><kbd>K</kbd> open anywhere</span>
        </footer>
      </div>
    </div>
  );
}
