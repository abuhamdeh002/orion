import { LINES, STARS } from "./orion";

/** ORION's mark: the constellation itself, Betelgeuse warm and Rigel cool. */
export function Logo({ size = 28, spin = true }: { size?: number; spin?: boolean }) {
  const at = (value: number) => 24 + value * 17;
  return (
    <svg className={spin ? "logo is-live" : "logo"} width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <circle cx="24" cy="24" r="22" className="logo-ring" />
      {LINES.map(([from, to], index) => (
        <line
          key={index}
          x1={at(STARS[from].x)}
          y1={at(STARS[from].y)}
          x2={at(STARS[to].x)}
          y2={at(STARS[to].y)}
          className="logo-line"
        />
      ))}
      {STARS.map((star, index) => (
        <circle
          key={star.name}
          cx={at(star.x)}
          cy={at(star.y)}
          r={0.9 + star.size * 1.35}
          className={`logo-star tone-${star.tone}`}
          style={{ animationDelay: `${index * 0.37}s` }}
        />
      ))}
    </svg>
  );
}
