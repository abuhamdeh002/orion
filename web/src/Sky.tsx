import { useEffect, useRef } from "react";

export type Mood = "idle" | "thinking" | "error";

type Star = { x: number; y: number; r: number; t: number; d: number; tint: 0 | 1 | 2 };
type Meteor = { x: number; y: number; vx: number; vy: number; life: number };

export function Sky({ mood }: { mood: Mood }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const moodRef = useRef(mood);
  moodRef.current = mood;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let width = 0;
    let height = 0;
    let stars: Star[] = [];
    let meteor: Meteor | null = null;
    let colors = { star: "#dfe9ff", accent: "#5eead4", warm: "#ffc98b", strength: 1 };
    const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
    let time = 0;
    let frame = 0;
    let running = true;
    let glow = 0;

    const readColors = () => {
      const style = getComputedStyle(document.documentElement);
      colors = {
        star: style.getPropertyValue("--star").trim() || colors.star,
        accent: style.getPropertyValue("--accent").trim() || colors.accent,
        warm: style.getPropertyValue("--warm").trim() || colors.warm,
        strength: Number(style.getPropertyValue("--sky-strength").trim() || 1),
      };
    };

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.round((width * height) / 4800);
      stars = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() * 1.1 + 0.25,
        t: Math.random() * Math.PI * 2,
        d: Math.random() * 0.8 + 0.2,
        // Real skies are not all white: a few blue-white, a few amber.
        tint: (Math.random() < 0.12 ? 1 : Math.random() < 0.08 ? 2 : 0) as 0 | 1 | 2,
      }));
    };

    // Frame budget: the model shares this GPU, so animation must stay cheap.
    // 20 fps while the window has focus, 6 fps when it doesn't.
    let lastFrame = 0;
    const draw = () => {
      if (!running) return;
      const stamp = performance.now();
      const budget = document.hasFocus() ? 50 : 166;
      if (!still && stamp - lastFrame < budget) {
        requestAnimationFrame(draw);
        return;
      }
      lastFrame = stamp;
      frame += 1;
      if (frame % 30 === 1) readColors();
      time += 0.016;
      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;
      const mood = moodRef.current;
      const target = mood === "thinking" ? 1 : mood === "error" ? 0.4 : 0.15;
      glow += (target - glow) * 0.04;
      context.clearRect(0, 0, width, height);

      for (const star of stars) {
        context.fillStyle = star.tint === 1 ? colors.accent : star.tint === 2 ? colors.warm : colors.star;
        const twinkle = 0.3 + 0.7 * Math.abs(Math.sin(star.t + time * star.d * 1.4));
        context.globalAlpha = twinkle * (0.55 + glow * 0.25) * colors.strength;
        context.beginPath();
        context.arc(star.x + pointer.x * star.d * 14, star.y + pointer.y * star.d * 14, star.r, 0, Math.PI * 2);
        context.fill();
      }

      if (!meteor && Math.random() < 0.0035) {
        meteor = { x: Math.random() * width * 0.7, y: Math.random() * height * 0.3, vx: 7, vy: 3.2, life: 1 };
      }
      if (meteor) {
        const tail = context.createLinearGradient(meteor.x, meteor.y, meteor.x - meteor.vx * 12, meteor.y - meteor.vy * 12);
        tail.addColorStop(0, colors.star);
        tail.addColorStop(1, "transparent");
        context.globalAlpha = meteor.life * 0.8 * colors.strength;
        context.strokeStyle = tail;
        context.lineWidth = 1.4;
        context.beginPath();
        context.moveTo(meteor.x, meteor.y);
        context.lineTo(meteor.x - meteor.vx * 12, meteor.y - meteor.vy * 12);
        context.stroke();
        meteor.x += meteor.vx;
        meteor.y += meteor.vy;
        meteor.life -= 0.018;
        if (meteor.life <= 0) meteor = null;
      }

      context.globalAlpha = 1;
      if (!still) requestAnimationFrame(draw);
    };

    const move = (event: PointerEvent) => {
      pointer.tx = event.clientX / width - 0.5;
      pointer.ty = event.clientY / height - 0.5;
    };

    resize();
    readColors();
    draw();
    const redraw = () => {
      resize();
      if (still) draw();
    };
    window.addEventListener("resize", redraw);
    window.addEventListener("pointermove", move);
    const observer = new MutationObserver(() => {
      readColors();
      if (still) draw();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      running = false;
      window.removeEventListener("resize", redraw);
      window.removeEventListener("pointermove", move);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={ref} className="sky" aria-hidden="true" />;
}
