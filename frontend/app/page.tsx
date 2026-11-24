import Link from "next/link";
import { Screen } from "@/components/app/screen";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRightIcon,
  BarcodeIcon,
  ScanIcon,
  ShieldCheckIcon,
  SparkleIcon,
} from "@/components/ui/icons";
import { VerdictGlyph } from "@/components/ui/verdict-glyph";
import { cn } from "@/lib/cn";
import { RECENT_CHECKS, STATS } from "@/lib/genie/mock";
import { TONE_CLASS, VERDICT_META } from "@/lib/genie/verdict";

export default function HomePage() {
  return (
    <Screen>
      <header className="flex items-center justify-between pt-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-pill bg-accent text-accent-ink">
            <SparkleIcon className="h-5 w-5" />
          </span>
          <div>
            <p className="text-lg font-bold leading-none tracking-tight">genie</p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
              verify before you buy
            </p>
          </div>
        </div>
        <Badge tone="accent" dot>
          demo
        </Badge>
      </header>

      <section className="relative overflow-hidden rounded-card border border-accent bg-accent p-6 text-accent-ink">
        <span className="absolute -right-5 -top-5 flex h-24 w-24 items-center justify-center rounded-pill bg-accent-ink/10">
          <SparkleIcon className="h-12 w-12" />
        </span>
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] opacity-70">
          Counterfeit check
        </p>
        <h1 className="mt-2 text-[36px] font-bold leading-none tracking-tight">
          Is it real?
        </h1>
        <p className="mt-3 max-w-[30ch] text-sm font-medium leading-relaxed opacity-80">
          Scan a pack. Genie cross-checks packaging, NAFDAC records, barcodes and
          batch data in seconds.
        </p>

        <div className="mt-6 flex flex-col gap-2.5">
          <Link
            href="/scan"
            className="inline-flex h-14 w-full items-center justify-center gap-2.5 rounded-pill bg-ink text-base font-semibold text-fg transition active:scale-[0.98]"
          >
            <ScanIcon className="h-5 w-5" /> Scan a product
          </Link>
          <div className="grid grid-cols-2 gap-2.5">
            <Link
              href="/scan"
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-pill border border-accent-ink/25 bg-accent-ink/10 px-4 text-sm font-semibold transition active:scale-[0.97]"
            >
              <BarcodeIcon className="h-4 w-4" /> Barcode
            </Link>
            <Link
              href="/scan"
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-pill border border-accent-ink/25 bg-accent-ink/10 px-4 text-sm font-semibold transition active:scale-[0.97]"
            >
              <ShieldCheckIcon className="h-4 w-4" /> NAFDAC
            </Link>
          </div>
        </div>
      </section>

      <section>
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Trust pulse</h2>
          <span className="text-[11px] text-muted">live intelligence</span>
        </div>
        <div className="grid grid-cols-3 gap-2.5">
          {STATS.map((stat) => (
            <div
              key={stat.label}
              className="rounded-card border border-line bg-card p-3.5"
            >
              <p className="text-xl font-bold tracking-tight">{stat.value}</p>
              <p className="mt-1 text-[10px] leading-tight text-muted">
                {stat.label}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Recent checks</h2>
          <Link
            href="/history"
            className="flex items-center gap-1 text-xs font-semibold text-accent"
          >
            See all <ArrowRightIcon className="h-3.5 w-3.5" />
          </Link>
        </div>
        <div className="flex flex-col gap-2.5">
          {RECENT_CHECKS.slice(0, 3).map((check) => {
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
      </section>
    </Screen>
  );
}
