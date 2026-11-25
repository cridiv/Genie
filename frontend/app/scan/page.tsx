"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@ui-sdk/react/button";
import { startRouteProgress } from "@/components/app/route-progress";
import { ScanCamera } from "@/components/scan/scan-camera";
import { Shot } from "@/components/scan/shot";
import { StepBar } from "@/components/scan/step-bar";
import {
  AlertIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  RefreshIcon,
} from "@/components/ui/icons";
import { verifyCapturedImage } from "@/lib/genie/api";
import type { VerificationResult } from "@/lib/genie/types";
import { inspectFrame, type ScanShots, type ScanSide } from "@/lib/scan/frame";
import { rememberShots } from "@/lib/scan/shots";

type Step = ScanSide | "analysing" | "done" | "error";

const EMPTY_SHOTS: ScanShots = { front: null, back: null };

function progressFor(step: Step, failed: ScanSide | null) {
  if (step === "front") return 1;
  if (step === "back") return 2;
  if (step === "error") return failed === "back" ? 2 : 1;
  return 3;
}

export default function ScanPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("front");
  const [shots, setShots] = useState<ScanShots>(EMPTY_SHOTS);
  const [rejected, setRejected] = useState<{
    side: ScanSide;
    shot: string;
    message?: string;
  } | null>(null);
  const [liveResult, setLiveResult] = useState<VerificationResult | null>(null);
  const busy = useRef(false);

  const side: ScanSide | null = step === "front" || step === "back" ? step : null;

  useEffect(() => {
    if (step !== "analysing") return;
    const primaryShot = shots.front || shots.back;
    if (!primaryShot) {
      setStep("front");
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await verifyCapturedImage(primaryShot);
        if (cancelled) return;
        setLiveResult(res);
        setStep("done");
      } catch (err) {
        if (cancelled) return;
        setRejected({
          side: "front",
          shot: primaryShot,
          message:
            err instanceof Error
              ? err.message
              : "Could not reach verification server. Please retry.",
        });
        setStep("error");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [step, shots.front, shots.back]);

  async function handleFrame(dataUrl: string) {
    if (busy.current) return;
    busy.current = true;

    const from: ScanSide = step === "back" ? "back" : "front";

    try {
      const readable = await inspectFrame(dataUrl);

      if (!readable) {
        setRejected({ side: from, shot: dataUrl, message: "Image unclear" });
        setStep("error");
        return;
      }

      setShots((previous) => ({ ...previous, [from]: dataUrl }));
      setStep(from === "back" ? "analysing" : "back");
    } finally {
      busy.current = false;
    }
  }

  function retry() {
    const from = rejected?.side ?? "front";
    setRejected(null);
    setLiveResult(null);
    setStep(from);
  }

  function restart() {
    setRejected(null);
    setLiveResult(null);
    setShots(EMPTY_SHOTS);
    setStep("front");
  }

  function goBack() {
    if (step === "back") {
      setStep("front");
      return;
    }
    startRouteProgress();
    router.push("/");
  }

  return (
    <main className="flex min-h-dvh flex-col gap-4 bg-ink px-4">
      <header className="flex items-center gap-3 pt-[max(1rem,env(safe-area-inset-top))]">
        {step === "analysing" ? (
          <span className="h-11 w-11 shrink-0" aria-hidden />
        ) : (
          <Button
            aria-label="Go back"
            onClick={goBack}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-pill border border-line bg-surface text-fg transition-transform duration-150 ease-out active:scale-95"
          >
            <ChevronLeftIcon className="h-5 w-5" />
          </Button>
        )}

        <div className="flex flex-1 items-center rounded-pill border border-line bg-surface px-4 py-3.5">
          <StepBar
            progress={progressFor(step, rejected?.side ?? null)}
            slow={step === "analysing"}
          />
        </div>
      </header>

      {side ? (
        <ScanCamera side={side} shots={shots} onFrame={handleFrame} />
      ) : (
        <div className="flex flex-1 flex-col">
          <AnimatePresence mode="wait">
            {step === "analysing" ? (
              <motion.div
                key="analysing"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -14 }}
                transition={{ duration: 0.26, ease: "easeOut" }}
                className="flex flex-1 flex-col"
              >
                <AnalysingScreen shots={shots} />
              </motion.div>
            ) : step === "done" ? (
              <motion.div
                key="done"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -14 }}
                transition={{ duration: 0.26, ease: "easeOut" }}
                className="flex flex-1 flex-col"
              >
                <DoneScreen
                  shots={shots}
                  productName={liveResult?.matchedProduct?.brandName}
                  onView={() => {
                    rememberShots(shots);
                    startRouteProgress();
                    const targetId = liveResult?.id || "authentic";
                    router.push(`/result/${encodeURIComponent(targetId)}`);
                  }}
                  onAgain={restart}
                />
              </motion.div>
            ) : rejected ? (
              <motion.div
                key="error"
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -14 }}
                transition={{ duration: 0.26, ease: "easeOut" }}
                className="flex flex-1 flex-col"
              >
                <ErrorScreen
                  shot={rejected.shot}
                  message={rejected.message}
                  onRetry={retry}
                />
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      )}
    </main>
  );
}

function AnalysingScreen({ shots }: { shots: ScanShots }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8">
      <div className="relative flex h-44 w-44 items-center justify-center">
        <svg
          viewBox="0 0 100 100"
          aria-hidden
          className="absolute inset-0 h-full w-full animate-spin motion-reduce:animate-none"
          style={{ animationDuration: "2.8s" }}
        >
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="78 205"
            className="stroke-accent"
          />
        </svg>

        <div className="flex items-center gap-2">
          {shots.front && (
            <motion.div
              initial={{ opacity: 0, x: 12, rotate: -12 }}
              animate={{ opacity: 1, x: 0, rotate: -6 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="h-20 w-16 overflow-hidden rounded-[14px] border border-line"
            >
              <Shot src={shots.front} />
            </motion.div>
          )}
          {shots.back && (
            <motion.div
              initial={{ opacity: 0, x: -12, rotate: 12 }}
              animate={{ opacity: 1, x: 0, rotate: 6 }}
              transition={{ duration: 0.35, ease: "easeOut" }}
              className="h-20 w-16 overflow-hidden rounded-[14px] border border-line"
            >
              <Shot src={shots.back} />
            </motion.div>
          )}
        </div>
      </div>

      <div className="text-center">
        <h1 className="font-display text-2xl font-bold tracking-tight">Verifying</h1>
        <p className="mt-1 text-xs text-muted">
          Checking NAFDAC registry, packaging references &amp; recalls…
        </p>
      </div>
    </div>
  );
}

function DoneScreen({
  shots,
  productName,
  onView,
  onAgain,
}: {
  shots: ScanShots;
  productName?: string;
  onView: () => void;
  onAgain: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
      <div className="relative flex h-28 w-28 items-center justify-center">
        <span className="absolute inset-0 rounded-pill bg-accent/20 animate-ping-slow" />
        <motion.span
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 320, damping: 15 }}
          className="relative flex h-20 w-20 items-center justify-center rounded-pill bg-accent text-accent-ink"
        >
          <CheckIcon className="h-9 w-9" />
        </motion.span>
      </div>

      <div>
        <h1 className="font-display text-3xl font-bold leading-tight tracking-tight">
          Scan complete
        </h1>
        {productName && (
          <p className="mt-1 text-sm text-muted">{productName}</p>
        )}
      </div>

      <div className="flex items-center gap-2">
        {shots.front && (
          <div className="h-16 w-14 overflow-hidden rounded-[14px] border border-line">
            <Shot src={shots.front} />
          </div>
        )}
        {shots.back && (
          <div className="h-16 w-14 overflow-hidden rounded-[14px] border border-line">
            <Shot src={shots.back} />
          </div>
        )}
      </div>

      <div className="flex w-full max-w-[300px] flex-col items-center gap-1.5">
        <Button
          onClick={onView}
          className="flex h-14 w-full items-center justify-center gap-2 rounded-pill bg-accent text-base font-semibold text-accent-ink transition-transform duration-150 ease-out active:scale-[0.98]"
        >
          View results
          <ArrowRightIcon className="h-4 w-4" />
        </Button>

        <Button
          onClick={onAgain}
          className="rounded-pill px-4 py-2 text-sm font-semibold text-muted transition-opacity duration-150 active:opacity-60"
        >
          Scan again
        </Button>
      </div>
    </div>
  );
}

function ErrorScreen({
  shot,
  message,
  onRetry,
}: {
  shot: string;
  message?: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
      <div className="relative h-32 w-28">
        <div className="h-full w-full overflow-hidden rounded-[22px] border border-line opacity-40">
          <Shot src={shot} />
        </div>
        <span className="absolute inset-0 flex items-center justify-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-pill bg-warn text-ink">
            <AlertIcon className="h-5 w-5" />
          </span>
        </span>
      </div>

      <div className="max-w-xs">
        <h1 className="font-display text-2xl font-bold tracking-tight">
          {message && message !== "Image unclear" ? "Verification failed" : "Image unclear"}
        </h1>
        {message && message !== "Image unclear" && (
          <p className="mt-1.5 text-xs text-muted">{message}</p>
        )}
      </div>

      <Button
        onClick={onRetry}
        className="flex h-14 w-full max-w-[300px] items-center justify-center gap-2 rounded-pill bg-accent text-base font-semibold text-accent-ink transition-transform duration-150 ease-out active:scale-[0.98]"
      >
        <RefreshIcon className="h-4 w-4" />
        Retry
      </Button>
    </div>
  );
}
