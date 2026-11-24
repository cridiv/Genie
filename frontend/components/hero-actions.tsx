"use client";

import { useState } from "react";
import type { ComponentType } from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type TargetAndTransition,
  type Transition,
  type Variants,
} from "framer-motion";
import { Button } from "@ui-sdk/react/button";
import {
  ArrowRightIcon,
  ScanIcon,
  ShieldCheckIcon,
  StoreIcon,
} from "@/components/ui/icons";

type Action = {
  label: string;
  icon: ComponentType<{ className?: string }>;
  primary?: boolean;
};

const actions: Action[] = [
  { label: "Scan product", icon: ScanIcon, primary: true },
  { label: "View verified pharmacy", icon: StoreIcon },
  { label: "View verifiable products", icon: ShieldCheckIcon },
];

const list: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.075, delayChildren: 0.08 } },
};

const item: Variants = {
  hidden: (dir: number) => ({ opacity: 0, y: 26, skewX: 14 * dir, scale: 0.9 }),
  show: (dir: number) => ({
    opacity: 1,
    y: 0,
    skewX: 6 * dir,
    scale: 1,
    transition: { type: "spring", stiffness: 380, damping: 15, mass: 0.9 },
  }),
};

const startExit: TargetAndTransition = {
  opacity: 0,
  y: -16,
  skewX: -12,
  scale: 0.86,
  transition: { duration: 0.26, ease: "easeIn" },
};

const floatTransition = (index: number): Transition => ({
  duration: 3.2 + index * 0.25,
  repeat: Infinity,
  ease: "easeInOut",
  delay: 0.7 + index * 0.12,
});

export function HeroActions() {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();

  return (
    <div className="flex w-full max-w-[340px] flex-col items-center">
      <AnimatePresence mode="wait">
        {open ? (
          <motion.div
            key="actions"
            variants={list}
            initial="hidden"
            animate="show"
            className="flex w-full flex-col gap-3"
          >
            {actions.map((action, index) => {
              const Icon = action.icon;
              // Alternate the lean so neighbouring pills tilt away from each other.
              const skew = reduced ? 0 : index % 2 === 0 ? -1 : 1;

              return (
                <motion.div
                  key={action.label}
                  variants={item}
                  custom={skew}
                  className="w-full"
                >
                  <motion.div
                    animate={reduced ? undefined : { y: [0, -4, 0] }}
                    transition={reduced ? undefined : floatTransition(index)}
                  >
                    <Button
                      className={
                        action.primary
                          ? "flex h-14 w-full items-center gap-3 rounded-pill bg-accent pl-2 pr-5 text-[15px] font-semibold text-accent-ink transition-transform duration-200 ease-out active:scale-[0.97]"
                          : "flex h-14 w-full items-center gap-3 rounded-pill border border-line bg-surface pl-2 pr-5 text-[15px] font-semibold text-fg transition-transform duration-200 ease-out active:scale-[0.97]"
                      }
                    >
                      <span
                        className={
                          action.primary
                            ? "flex h-10 w-10 shrink-0 items-center justify-center rounded-pill bg-ink text-accent"
                            : "flex h-10 w-10 shrink-0 items-center justify-center rounded-pill bg-card text-accent"
                        }
                      >
                        <Icon className="h-5 w-5" />
                      </span>
                      <span className="flex-1 text-left">{action.label}</span>
                      <ArrowRightIcon
                        className={
                          action.primary
                            ? "h-4 w-4 shrink-0 text-ink/45"
                            : "h-4 w-4 shrink-0 text-muted"
                        }
                      />
                    </Button>
                  </motion.div>
                </motion.div>
              );
            })}
          </motion.div>
        ) : (
          <motion.div key="start" initial={false} exit={startExit}>
            <Button
              onClick={() => setOpen(true)}
              className="group flex h-14 items-center gap-3 rounded-pill bg-accent pl-7 pr-2 text-base font-semibold text-accent-ink transition-transform duration-200 ease-out active:scale-[0.97]"
            >
              Start
              <span className="flex h-10 w-10 items-center justify-center rounded-pill bg-ink text-accent transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-active:translate-x-1">
                <ArrowRightIcon className="h-4 w-4" />
              </span>
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
