"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ResultView } from "@/components/result/result-view";
import { AppHeader } from "@/components/app/app-header";
import { Screen } from "@/components/app/screen";
import { fetchScanById, loadLiveResult } from "@/lib/genie/api";
import type { VerificationResult } from "@/lib/genie/types";

export function LiveResultLoader({
  scanId,
  initialResult,
}: {
  scanId: string;
  initialResult: VerificationResult | null;
}) {
  const [result, setResult] = useState<VerificationResult | null>(initialResult);
  const [loading, setLoading] = useState<boolean>(!initialResult);

  useEffect(() => {
    if (initialResult) return;

    const cached = loadLiveResult(scanId);
    if (cached) {
      setResult(cached);
      setLoading(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const fetched = await fetchScanById(scanId);
        if (!cancelled) setResult(fetched);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [scanId, initialResult]);

  if (loading) {
    return (
      <Screen>
        <AppHeader title="Verification result" subtitle="Loading saved scan…" />
        <div className="rounded-card border border-line bg-card p-6 text-center text-sm text-muted">
          Fetching scan {scanId}…
        </div>
      </Screen>
    );
  }

  if (!result) {
    return (
      <Screen>
        <AppHeader title="Scan not found" subtitle={scanId} />
        <div className="rounded-card border border-line bg-card p-6 text-center">
          <p className="text-sm text-muted">
            We couldn&apos;t load scan <span className="font-mono">{scanId}</span>.
          </p>
          <Link
            href="/scan"
            className="mt-4 inline-flex h-11 items-center justify-center rounded-pill bg-accent px-5 text-sm font-semibold text-accent-ink"
          >
            Scan a medicine
          </Link>
        </div>
      </Screen>
    );
  }

  return <ResultView result={result} />;
}
