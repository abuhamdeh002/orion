import { useEffect } from "react";
import { LINES, STARS } from "./orion";

/** Opening: the stars appear one by one, the figure is drawn between them, then the name. */
export function Intro({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 2900);
    return () => window.clearTimeout(timer);
  }, [onDone]);

  const at = (value: number) => 100 + value * 72;
  return (
    <div className="intro" onClick={onDone} role="presentation">
      <svg className="intro-figure" viewBox="0 0 200 200" aria-hidden="true">
        {LINES.map(([from, to], index) => (
          <line
            key={index}
            x1={at(STARS[from].x)}
            y1={at(STARS[from].y)}
            x2={at(STARS[to].x)}
            y2={at(STARS[to].y)}
            pathLength={1}
            className="intro-line"
            style={{ animationDelay: `${0.75 + index * 0.08}s` }}
          />
        ))}
        {STARS.map((star, index) => (
          <g key={star.name} className={`intro-star tone-${star.tone}`} style={{ animationDelay: `${0.1 + index * 0.075}s` }}>
            <circle cx={at(star.x)} cy={at(star.y)} r={7 + star.size * 6} className="intro-halo" />
            <circle cx={at(star.x)} cy={at(star.y)} r={1.4 + star.size * 1.6} />
          </g>
        ))}
      </svg>
      <div className="intro-word">
        {"Orion".split("").map((letter, index) => (
          <span key={index} style={{ animationDelay: `${1.35 + index * 0.06}s` }}>
            {letter}
          </span>
        ))}
      </div>
      <div className="intro-sub">present in the day</div>
    </div>
  );
}
