import { useEffect, useRef } from "react";
import { live } from "./levels";
import { BELT, LINES, STARS } from "./orion";

/**
 * ORION's presence: the Orion constellation, alive.
 * idle breathes · listening sends ripples out · thinking runs light along the lines ·
 * speaking wraps it in a warm voice wave · error dims it.
 */
export function Presence({ phase }: { phase: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const context = node.getContext("2d");
    if (!context) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let size = 320;
    let running = true;
    let frame = 0;
    let colors = { accent: "#9ec5ff", warm: "#ff8f5e", star: "#eef2ff", violet: "#a78bfa", muted: "#8b93ab" };
    // On a pale page, additive glow turns to grey smudges; light gets plain blending and tighter halos.
    let light = false;
    const energy = { listen: 0, think: 0, speak: 0, err: 0 };
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    const born = performance.now();

    const readColors = () => {
      const style = getComputedStyle(document.documentElement);
      const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
      light = document.documentElement.dataset.theme === "light";
      colors = {
        accent: read("--accent", colors.accent),
        warm: read("--warm", colors.warm),
        star: read("--star", colors.star),
        violet: read("--violet", colors.violet),
        muted: read("--muted", colors.muted),
      };
    };

    const fit = () => {
      const box = node.parentElement?.getBoundingClientRect();
      size = Math.max(160, Math.round(Math.min(box?.width || 320, box?.height || 320)));
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      node.width = size * ratio;
      node.height = size * ratio;
      node.style.width = `${size}px`;
      node.style.height = `${size}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };

    const glowDot = (x: number, y: number, radius: number, color: string, alpha: number) => {
      const halo = context.createRadialGradient(x, y, 0, x, y, radius);
      halo.addColorStop(0, color);
      halo.addColorStop(1, "transparent");
      context.globalAlpha = Math.max(0, Math.min(1, alpha));
      context.fillStyle = halo;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    };

    /** A voice-like envelope: syllables inside words inside phrases. */
    const envelope = (t: number) => {
      const syllable = Math.abs(Math.sin(t * 9.1) * Math.sin(t * 3.7 + 0.6));
      const phrase = 0.55 + 0.45 * Math.sin(t * 0.9 + Math.sin(t * 0.37));
      return Math.min(1, 0.18 + syllable * phrase * 1.1);
    };

    // Frame budget: the model shares this GPU, so animation must stay cheap.
    // 30 fps while the window has focus, 8 fps when it doesn't.
    let lastFrame = 0;
    const draw = () => {
      if (!running) return;
      const stamp = performance.now();
      const budget = document.hasFocus() ? 33 : 125;
      if (!still && stamp - lastFrame < budget) {
        requestAnimationFrame(draw);
        return;
      }
      lastFrame = stamp;
      frame += 1;
      if (frame % 40 === 1) readColors();
      const t = (performance.now() - born) / 1000;
      const current = phaseRef.current;
      const target = {
        listen: current === "listening" ? 1 : 0,
        think: current === "thinking" || current === "linking" ? 1 : 0,
        speak: current === "speaking" ? 1 : 0,
        err: current === "error" ? 1 : 0,
      };
      for (const key of Object.keys(energy) as (keyof typeof energy)[]) {
        energy[key] += (target[key] - energy[key]) * (still ? 1 : 0.06);
      }
      pointer.x += (pointer.tx - pointer.x) * 0.05;
      pointer.y += (pointer.ty - pointer.y) * 0.05;

      const { listen, think, speak, err } = energy;
      const cx = size / 2;
      const cy = size / 2 + Math.sin(t * 0.8) * size * 0.006;
      const unit = size / 320;
      // Real sound when the PC sends it: the room's loudness, and his own voice as it plays.
      const fresh = live.connected && performance.now() - live.at < 1200;
      const hearing = fresh ? live.mic : 0;
      const radius = size * 0.355 * (1 + listen * 0.035 + hearing * listen * 0.07);
      const voice = speak > 0.01 && fresh && live.out !== null ? Math.max(0.1, Math.min(1, live.out * 1.4)) : envelope(t);
      const dim = 1 - err * 0.55;
      const breath = 0.5 + 0.5 * Math.sin(t * 1.1);
      context.clearRect(0, 0, size, size);
      context.globalCompositeOperation = light ? "source-over" : "lighter";
      const glowScale = light ? 0.45 : 1;

      // Halo: cool by default, warm while he talks.
      glowDot(cx, cy, size * 0.5, colors.accent, (0.1 + breath * 0.05 + listen * 0.06 + hearing * 0.16) * dim * glowScale);
      if (speak > 0.01) glowDot(cx, cy, size * 0.48, colors.warm, speak * (0.1 + voice * 0.12));
      if (think > 0.01) glowDot(cx, cy, size * 0.42, colors.violet, think * 0.12);

      // Orbit: a quiet ring, dashed and turning while he thinks.
      context.lineWidth = 1;
      context.strokeStyle = think > 0.2 ? colors.violet : colors.star;
      context.globalAlpha = (0.08 + think * 0.35) * dim;
      context.setLineDash(think > 0.05 ? [radius * 0.42, radius * 0.24] : []);
      context.lineDashOffset = -t * 70;
      context.beginPath();
      context.arc(cx, cy, radius * 1.3, 0, Math.PI * 2);
      context.stroke();
      context.setLineDash([]);

      // Listening: ripples travel out from the figure.
      if (listen > 0.01) {
        context.strokeStyle = colors.accent;
        for (let ring = 0; ring < 3; ring += 1) {
          const progress = (t * 0.55 + ring / 3) % 1;
          context.lineWidth = (1.4 + hearing * 2.2) * (1 - progress) + 0.3;
          context.globalAlpha = listen * (1 - progress) ** 2 * (0.45 + hearing * 0.55);
          context.beginPath();
          context.arc(cx, cy, radius * (0.9 + progress * 0.5), 0, Math.PI * 2);
          context.stroke();
        }
      }

      // Speaking: a voice wave around him, two strands.
      if (speak > 0.01) {
        for (const [color, shift, weight] of [
          [colors.warm, 0, 1],
          [colors.accent, 1.7, 0.6],
        ] as [string, number, number][]) {
          context.strokeStyle = color;
          context.lineWidth = 1.6 * weight;
          context.globalAlpha = speak * 0.75 * weight;
          context.beginPath();
          const steps = 220;
          for (let step = 0; step <= steps; step += 1) {
            const theta = (step / steps) * Math.PI * 2;
            const wave =
              Math.sin(6 * theta + t * 4.2 + shift) * 0.5 +
              Math.sin(11 * theta - t * 6.3 + shift) * 0.3 +
              Math.sin(19 * theta + t * 9.4) * 0.2;
            const distance = radius * 1.12 + wave * radius * 0.12 * voice * speak;
            const x = cx + Math.cos(theta) * distance;
            const y = cy + Math.sin(theta) * distance;
            if (step === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
          }
          context.closePath();
          context.stroke();
        }
      }

      // The figure turns a little in space, and follows the pointer.
      const yaw = Math.sin(t * 0.23) * 0.26 + pointer.x * 0.35;
      const pitch = Math.sin(t * 0.17) * 0.08 + pointer.y * 0.2;
      const points = STARS.map((star) => {
        const x1 = star.x * Math.cos(yaw);
        const z1 = star.x * Math.sin(yaw);
        const y2 = star.y * Math.cos(pitch) - z1 * Math.sin(pitch);
        const z2 = star.y * Math.sin(pitch) + z1 * Math.cos(pitch);
        const depth = 1 / (1 + z2 * 0.28);
        return { x: cx + x1 * radius * depth, y: cy + y2 * radius * depth, depth };
      });

      // Lines.
      context.lineWidth = 1.1 * unit + 0.25;
      context.strokeStyle = err > 0.5 ? colors.muted : colors.star;
      LINES.forEach(([from, to]) => {
        const a = points[from];
        const b = points[to];
        const line = context.createLinearGradient(a.x, a.y, b.x, b.y);
        line.addColorStop(0, colors.star);
        line.addColorStop(0.5, colors.accent);
        line.addColorStop(1, colors.star);
        context.strokeStyle = err > 0.5 ? colors.muted : line;
        context.globalAlpha = (0.34 + listen * 0.2 + think * 0.16 + speak * voice * 0.2) * dim;
        context.beginPath();
        context.moveTo(a.x, a.y);
        context.lineTo(b.x, b.y);
        context.stroke();
      });

      // Thinking: light runs along the lines.
      if (think > 0.01) {
        LINES.forEach(([from, to], line) => {
          const progress = (t * 0.7 + line * 0.19) % 1;
          const a = points[from];
          const b = points[to];
          const x = a.x + (b.x - a.x) * progress;
          const y = a.y + (b.y - a.y) * progress;
          glowDot(x, y, 9 * unit, colors.violet, think * 0.9 * Math.sin(progress * Math.PI));
        });
      }

      // Stars.
      STARS.forEach((star, index) => {
        const point = points[index];
        let shine = 0.72 + 0.28 * Math.sin(t * 1.6 + index * 1.37);
        shine += speak * voice * 0.4;
        const beltSpot = BELT.indexOf(index);
        if (beltSpot >= 0) shine += think * Math.max(0, Math.sin(t * 4.2 - beltSpot * 1.1)) * 0.8;
        shine *= dim;
        const tint = star.tone === "warm" ? colors.warm : star.tone === "cool" ? colors.accent : colors.star;
        const core = (1.6 + star.size * 2.6) * unit * point.depth;
        if (light) {
          glowDot(point.x, point.y, core * 4.5, tint, 0.22 * shine);
        } else {
          glowDot(point.x, point.y, core * 8, tint, 0.42 * shine);
          glowDot(point.x, point.y, core * 2.6, colors.star, 0.55 * shine);
        }
        context.globalAlpha = Math.min(1, 0.92 * shine + 0.1);
        context.fillStyle = light ? tint : colors.star;
        context.beginPath();
        context.arc(point.x, point.y, core, 0, Math.PI * 2);
        context.fill();
        if (star.size > 1) {
          // Diffraction spikes on the two bright ones, Betelgeuse and Rigel.
          context.strokeStyle = tint;
          context.lineWidth = 0.8;
          context.globalAlpha = 0.32 * shine;
          const reach = core * (5 + speak * voice * 3);
          context.beginPath();
          context.moveTo(point.x - reach, point.y);
          context.lineTo(point.x + reach, point.y);
          context.moveTo(point.x, point.y - reach);
          context.lineTo(point.x, point.y + reach);
          context.stroke();
        }
      });

      context.globalCompositeOperation = "source-over";
      context.globalAlpha = 1;
      if (!still) requestAnimationFrame(draw);
    };

    const move = (event: PointerEvent) => {
      pointer.tx = event.clientX / window.innerWidth - 0.5;
      pointer.ty = event.clientY / window.innerHeight - 0.5;
    };
    const resize = new ResizeObserver(() => {
      fit();
      if (still) draw();
    });
    if (node.parentElement) resize.observe(node.parentElement);
    const theme = new MutationObserver(readColors);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const visible = () => {
      const wasRunning = running;
      running = document.visibilityState === "visible";
      if (running && !wasRunning && !still) requestAnimationFrame(draw);
    };
    document.addEventListener("visibilitychange", visible);
    window.addEventListener("pointermove", move);
    fit();
    readColors();
    draw();
    const repaint = still ? window.setInterval(draw, 600) : 0;
    return () => {
      running = false;
      resize.disconnect();
      theme.disconnect();
      window.clearInterval(repaint);
      document.removeEventListener("visibilitychange", visible);
      window.removeEventListener("pointermove", move);
    };
  }, []);

  return <canvas ref={canvas} className="presence" aria-hidden="true" />;
}
