"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Screen } from "@/components/app/screen";
import { Badge } from "@/components/ui/badge";
import {
  CameraIcon,
  ChevronLeftIcon,
  ScanIcon,
} from "@/components/ui/icons";
import { PillButton } from "@/components/ui/pill";
import { cn } from "@/lib/cn";
import { SCENARIO_OPTIONS } from "@/lib/genie/mock";
import type { Scenario } from "@/lib/genie/types";

const CORNERS = [
  "left-5 top-5 rounded-tl-2xl border-l-2 border-t-2",
  "right-5 top-5 rounded-tr-2xl border-r-2 border-t-2",
  "bottom-5 left-5 rounded-bl-2xl border-b-2 border-l-2",
  "bottom-5 right-5 rounded-br-2xl border-b-2 border-r-2",
];

export default function ScanPage() {
  const router = useRouter();
  const [scenario, setScenario] = useState<Scenario>("authentic");
  const [mode, setMode] = useState<"camera" | "code">("camera");
  const [scanning, setScanning] = useState(false);

  function runCheck() {
    if (scanning) return;
    setScanning(true);
    window.setTimeout(() => router.push(`/result/${scenario}`), 1800);
  }

  return (
    <Screen className="gap-6">
      <header className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Go back"
          className="flex h-10 w-10 items-center justify-center rounded-pill border border-line bg-card transition active:scale-95"
        >
          <ChevronLeftIcon />
        </button>
        <p className="text-sm font-semibold">Scan product</p>
        <span className="h-10 w-10" aria-hidden />
      </header>

      <div className="relative aspect-[4/5] w-full overflow-hidden rounded-card border border-line bg-surface">
        {CORNERS.map((corner) => (
          <span
            key={corner}
            className={cn("absolute h-9 w-9 border-accent/70", corner)}
          />
        ))}

        <div className="absolute inset-0 flex items-center justify-center">
          <div
            className={cn(
              "flex h-28 w-24 flex-col items-center justify-center gap-2 rounded-[20px] border-2 border-dashed bg-card transition-colors",
              scanning ? "border-accent" : "border-line",
            )}
          >
            <ScanIcon className="h-8 w-8 text-muted" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted">
              pack
            </span>
          </div>
        </div>

        {scanning && (
          <div className="animate-scanline absolute inset-x-8 top-[16%] h-1 rounded-pill bg-accent" />
        )}

        <div className="absolute inset-x-0 bottom-0 flex justify-center p-5">
          <Badge tone={scanning ? "accent" : "muted"} dot>
            {scanning ? "Analyzing 5 signals…" : "Align the pack inside the frame"}
          </Badge>
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted">
            Demo scenario
          </p>
          <span className="text-[11px] text-muted">simulated</span>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {SCENARIO_OPTIONS.map((option) => {
            const active = scenario === option.id;
            return (
              <button
                key={option.id}
                type="button"
                disabled={scanning}
                onClick={() => setScenario(option.id)}
                className={cn(
                  "rounded-pill border px-4 py-3 text-left transition active:scale-[0.98] disabled:opacity-60",
                  active
                    ? "border-accent bg-accent/10"
                    : "border-line bg-card",
                )}
              >
                <span
                  className={cn(
                    "block text-sm font-semibold",
                    active ? "text-accent" : "text-fg",
                  )}
                >
                  {option.label}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-muted">
                  {option.hint}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {mode === "camera" ? (
        <div className="flex flex-col gap-2">
          <PillButton
            size="lg"
            className="w-full"
            onClick={runCheck}
            disabled={scanning}
          >
            <CameraIcon className="h-5 w-5" />
            {scanning ? "Reading pack…" : "Capture"}
          </PillButton>
          <PillButton
            variant="ghost"
            size="sm"
            onClick={() => setMode("code")}
            disabled={scanning}
          >
            Enter a code instead
          </PillButton>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          <input
            inputMode="text"
            autoComplete="off"
            placeholder="04-1928 or 5000456051231"
            className="h-14 w-full rounded-pill border border-line bg-card px-5 text-sm text-fg outline-none transition placeholder:text-muted focus:border-accent"
          />
          <PillButton
            size="lg"
            className="w-full"
            onClick={runCheck}
            disabled={scanning}
          >
            {scanning ? "Checking…" : "Check product"}
          </PillButton>
          <PillButton
            variant="ghost"
            size="sm"
            onClick={() => setMode("camera")}
            disabled={scanning}
          >
            Use the camera
          </PillButton>
        </div>
      )}
    </Screen>
  );
}
