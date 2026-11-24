"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

const TAU = Math.PI * 2;
const FRAME_MS = 1000 / 24;

/**
 * Canvas dot field with a slow diagonal ripple.
 *
 * Tuned for phones: throttled to ~24fps, DPR capped at 1.5, coarser spacing on
 * touch devices, paused while the tab is hidden, and drawn exactly once when
 * the visitor prefers reduced motion.
 */
export function DotGrid({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

    let width = 0;
    let height = 0;
    let gap = 30;
    let raf = 0;
    let lastStamp = 0;

    const draw = (time: number) => {
      if (!width || !height) return;

      ctx.clearRect(0, 0, width, height);

      const dots = new Path2D();
      const sparks = new Path2D();
      const drift = time * 0.0013;

      let row = 0;
      for (let y = gap * 0.5; y < height; y += gap, row++) {
        let col = 0;
        for (let x = gap * 0.5; x < width; x += gap, col++) {
          const wave = Math.sin((x + y) * 0.011 - drift);
          const radius = 0.8 + (wave + 1) * 0.55;
          const path = (col * 3 + row * 7) % 41 === 0 ? sparks : dots;

          path.moveTo(x + radius, y);
          path.arc(x, y, radius, 0, TAU);
        }
      }

      ctx.fillStyle = "#eef2f7";
      ctx.globalAlpha = 0.16;
      ctx.fill(dots);

      ctx.fillStyle = "#c8f65a";
      ctx.globalAlpha = 0.42;
      ctx.fill(sparks);
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      if (!width || !height) return;

      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      gap = width < 520 ? 26 : 34;
      lastStamp = 0;
      draw(performance.now());
    };

    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      if (now - lastStamp < FRAME_MS) return;
      lastStamp = now;
      draw(now);
    };

    const start = () => {
      if (!raf) raf = requestAnimationFrame(tick);
    };

    const stop = () => {
      if (!raf) return;
      cancelAnimationFrame(raf);
      raf = 0;
    };

    const onVisibility = () => {
      if (document.hidden) stop();
      else if (!reduced.matches) start();
    };

    const onReducedChange = () => {
      if (reduced.matches) {
        stop();
        draw(performance.now());
      } else if (!document.hidden) {
        start();
      }
    };

    resize();
    if (!reduced.matches) start();

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    document.addEventListener("visibilitychange", onVisibility);
    reduced.addEventListener("change", onReducedChange);

    return () => {
      stop();
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      reduced.removeEventListener("change", onReducedChange);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={cn("block h-full w-full", className)}
    />
  );
}
