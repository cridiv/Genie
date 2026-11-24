import type { Metadata } from "next";
import Link from "next/link";
import { AppHeader } from "@/components/app/app-header";
import { Screen } from "@/components/app/screen";
import { ArrowRightIcon } from "@/components/ui/icons";
import { VerdictGlyph } from "@/components/ui/verdict-glyph";
import { cn } from "@/lib/cn";
import { RECENT_CHECKS, STATS } from "@/lib/genie/mock";
import { TONE_CLASS, VERDICT_META } from "@/lib/genie/verdict";

export const metadata: Metadata = { title: "History" };

export default function HistoryPage() {
  return (
    <Screen>
      <AppHeader title="History" subtitle="Your recent verification checks" />

      <div className="grid grid-cols-3 gap-2.5">
        {STATS.map((stat) => (
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

      <div className="flex flex-col gap-2.5">
        {RECENT_CHECKS.map((check) => {
          const meta = VERDICT_META[check.verdict];
          return (
            <Link
              key={check.id}
              href={`/result/${check.scenario}`}
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

      <p className="text-center text-[11px] text-muted">
        Checks are stored on this device in demo mode.
      </p>
    </Screen>
  );
}
