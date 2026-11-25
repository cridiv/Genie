"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AppHeader } from "@/components/app/app-header";
import { Screen } from "@/components/app/screen";
import { ArrowRightIcon } from "@/components/ui/icons";
import { VerdictGlyph } from "@/components/ui/verdict-glyph";
import { cn } from "@/lib/cn";
import { fetchRecentScans } from "@/lib/genie/api";
import type { RecentCheck } from "@/lib/genie/types";
import { TONE_CLASS, VERDICT_META } from "@/lib/genie/verdict";

export default function HistoryPage() {
  const [checks, setChecks] = useState<RecentCheck[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await fetchRecentScans(25);
        if (!cancelled) {
          setChecks(rows);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError("Could not reach GENIE AI backend for scan history.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const authenticCount = checks.filter(
    (c) => c.verdict === "authentic" || c.verdict === "likely_authentic",
  ).length;
  const flaggedCount = checks.filter(
    (c) => c.verdict === "suspicious" || c.verdict === "likely_counterfeit",
  ).length;

  const stats = [
    { label: "Total scans", value: String(checks.length) },
    { label: "Verified real", value: String(authenticCount) },
    { label: "Flagged", value: String(flaggedCount) },
  ];

  return (
    <Screen>
      <AppHeader
        title="History"
        subtitle={loading ? "Loading live verification checks…" : "Live verification checks"}
      />

      <div className="grid grid-cols-3 gap-2.5">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-card border border-line bg-card p-3"
          >
            <p className="text-lg font-bold tracking-tight">{stat.value}</p>
            <p className="mt-0.5 text-[10px] leading-tight text-muted">
              {stat.label}
            </p>
          </div>
        ))}
      </div>

      {error ? (
        <div className="rounded-card border border-line bg-card p-4 text-xs text-muted">
          {error}
        </div>
      ) : loading ? (
        <div className="rounded-card border border-line bg-card p-4 text-xs text-muted">
          Fetching saved scans from GENIE AI…
        </div>
      ) : checks.length === 0 ? (
        <div className="rounded-card border border-line bg-card p-5 text-center">
          <p className="text-sm text-muted">No scans saved yet.</p>
          <Link
            href="/scan"
            className="mt-3 inline-flex h-10 items-center justify-center rounded-pill bg-accent px-4 text-xs font-semibold text-accent-ink"
          >
            Scan your first medicine
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {checks.map((check) => {
            const meta = VERDICT_META[check.verdict];
            return (
              <Link
                key={check.id}
                href={`/result/${encodeURIComponent(check.id)}`}
                className="flex items-center gap-3 rounded-pill border border-line bg-card px-4 py-3 transition active:scale-[0.99]"
              >
                <span
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-pill border",
                    TONE_CLASS[meta.tone].chip,
                  )}
                >
                  <VerdictGlyph verdict={check.verdict} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold">
                    {check.productName}
                  </span>
                  <span className="block text-xs text-muted">
                    {meta.label} · {check.when}
                  </span>
                </span>
                <ArrowRightIcon className="h-4 w-4 shrink-0 text-muted" />
              </Link>
            );
          })}
        </div>
      )}

      <p className="text-center text-[11px] text-muted">
        Synced live with GENIE AI scan database.
      </p>
    </Screen>
  );
}
