"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";

type Listener = (active: boolean) => void;

let active = false;
const listeners = new Set<Listener>();

function emit(next: boolean) {
  active = next;
  listeners.forEach((listener) => listener(next));
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot() {
  return active;
}

function getServerSnapshot() {
  return false;
}

/**
 * Start the bar for navigations that don't come from an <a> click, e.g. a
 * `router.push` fired by a button.
 */
export function startRouteProgress() {
  if (!active) emit(true);
}

function finishRouteProgress() {
  if (active) emit(false);
}

/** Decelerating ramp — it creeps toward the end but never quite arrives. */
const RAMP = [0.12, 0.28, 0.45, 0.62, 0.76, 0.86];

/** Prefetched navigations land faster than this, so they never flash the bar. */
const APPEAR_MS = 140;

export function RouteProgress() {
  const pathname = usePathname();
  const running = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timers: number[] = [];
    const push = (run: () => void, delay: number) => {
      timers.push(window.setTimeout(run, delay));
    };

    if (running) {
      push(() => setProgress(RAMP[0]), 0);

      RAMP.slice(1).forEach((value, index) => {
        push(() => setProgress(value), 160 * (index + 1));
      });

      push(() => setVisible(true), APPEAR_MS);
    } else {
      // Snap to full, fade out, then reset while it's invisible.
      push(() => setProgress(1), 0);
      push(() => setVisible(false), 200);
      push(() => setProgress(0), 420);
    }

    return () => {
      timers.forEach((id) => window.clearTimeout(id));
    };
  }, [running]);

  // Any completed navigation ends the bar, even when a click slipped past.
  useEffect(() => {
    finishRouteProgress();
  }, [pathname]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }

      const target = event.target;
      if (!(target instanceof Element)) return;

      const anchor = target.closest("a");
      if (!anchor) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;
      if (anchor.getAttribute("aria-disabled") === "true") return;

      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;

      const next = new URL(anchor.href, window.location.href);
      if (next.origin !== window.location.origin) return;
      if (
        next.pathname === window.location.pathname &&
        next.search === window.location.search
      ) {
        return;
      }

      startRouteProgress();
    }

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  // Never leave the bar stranded if a navigation never lands.
  useEffect(() => {
    if (!running) return;
    const guard = window.setTimeout(() => finishRouteProgress(), 10_000);
    return () => window.clearTimeout(guard);
  }, [running]);

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[60] flex justify-center">
      <div
        aria-hidden
        style={{ transform: `scaleX(${progress})`, opacity: visible ? 1 : 0 }}
        className="h-[3px] w-full max-w-[480px] origin-left rounded-r-pill bg-accent transition-[transform,opacity] duration-200 ease-out"
      />
    </div>
  );
}
