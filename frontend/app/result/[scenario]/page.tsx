import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppHeader } from "@/components/app/app-header";
import { Screen } from "@/components/app/screen";
import { Badge } from "@/components/ui/badge";
import {
  AlertIcon,
  ArrowRightIcon,
  CheckIcon,
  QuestionIcon,
  StoreIcon,
  XIcon,
} from "@/components/ui/icons";
import { PillLink } from "@/components/ui/pill";
import { VerdictGlyph } from "@/components/ui/verdict-glyph";
import { cn } from "@/lib/cn";
import { getResult, SCENARIO_VALUES } from "@/lib/genie/mock";
import type { Scenario, SignalStatus } from "@/lib/genie/types";
import { STATUS_META, TONE_CLASS, VERDICT_META } from "@/lib/genie/verdict";

function isScenario(value: string): value is Scenario {
  return (SCENARIO_VALUES as string[]).includes(value);
}

export function generateStaticParams() {
  return SCENARIO_VALUES.map((scenario) => ({ scenario }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ scenario: string }>;
}): Promise<Metadata> {
  const { scenario } = await params;
  if (!isScenario(scenario)) return { title: "Result" };
  return { title: VERDICT_META[getResult(scenario).verdict].label };
}

function StatusGlyph({ status }: { status: SignalStatus }) {
  if (status === "pass") return <CheckIcon className="h-4 w-4" />;
  if (status === "warn") return <AlertIcon className="h-4 w-4" />;
  if (status === "fail") return <XIcon className="h-4 w-4" />;
  return <QuestionIcon className="h-4 w-4" />;
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
      <dt className="shrink-0 text-xs text-muted">{label}</dt>
      <dd
        className={cn(
          "text-right text-xs font-semibold",
          mono && "font-mono tracking-tight",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

export default async function ResultPage({
  params,
}: {
  params: Promise<{ scenario: string }>;
}) {
  const { scenario } = await params;
  if (!isScenario(scenario)) notFound();

  const result = getResult(scenario);
  const meta = VERDICT_META[result.verdict];
  const product = result.matchedProduct;

  return (
    <Screen>
      <AppHeader
        title="Scan result"
        subtitle={`${Math.round(result.confidence * 100)}% confidence`}
      />

      <section
        className={cn("rounded-card p-6", TONE_CLASS[meta.tone].fill)}
      >
        <div className="flex items-start justify-between">
          <span className="flex h-14 w-14 items-center justify-center rounded-pill bg-black/10">
            <VerdictGlyph verdict={result.verdict} className="h-7 w-7" />
          </span>
          <span className="rounded-pill bg-black/10 px-3 py-1 text-xs font-bold">
            {Math.round(result.confidence * 100)}%
          </span>
        </div>
        <h1 className="mt-5 text-3xl font-bold leading-tight tracking-tight">
          {meta.label}
        </h1>
        <p className="mt-2 max-w-[34ch] text-sm font-medium leading-relaxed opacity-80">
          {meta.blurb}
        </p>
        <div className="mt-5 h-2 w-full overflow-hidden rounded-pill bg-black/10">
          <div
            className="h-full rounded-pill bg-current"
            style={{ width: `${Math.round(result.confidence * 100)}%` }}
          />
        </div>
      </section>

      {product ? (
        <div className="rounded-card border border-line bg-card p-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted">
              Matched record
            </p>
            <Badge
              tone={product.registrationStatus === "active" ? "ok" : "bad"}
              dot
            >
              NAFDAC {product.registrationStatus}
            </Badge>
          </div>
          <h2 className="mt-3 text-xl font-bold leading-tight">
            {product.brandName}
          </h2>
          <p className="text-sm text-muted">{product.genericName}</p>

          <dl className="mt-4 flex flex-col divide-y divide-line">
            <InfoRow label="Manufacturer" value={product.manufacturer} />
            <InfoRow label="NAFDAC no." value={product.nafdacNumber} mono />
            <InfoRow label="Strength" value={product.strength} />
            <InfoRow label="Dosage form" value={product.form} />
            {result.matchedVersion && (
              <InfoRow
                label="Pack version"
                value={`${result.matchedVersion.label}${
                  result.matchedVersion.isCurrent ? " · current" : " · historical"
                }`}
              />
            )}
          </dl>
        </div>
      ) : (
        <div className="rounded-card border border-line bg-card p-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted">
            Matched record
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            No verified product record matched this scan yet. Genie is
            investigating it against official sources.
          </p>
          {result.discoveryJobId && (
            <div className="mt-3 flex items-center justify-between rounded-pill border border-info/30 bg-info/10 px-4 py-2.5">
              <span className="text-xs font-semibold text-info">
                Investigation running
              </span>
              <span className="font-mono text-xs text-info">
                {result.discoveryJobId}
              </span>
            </div>
          )}
        </div>
      )}

      <section>
        <div className="mb-2.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Signal breakdown</h2>
          <span className="text-[11px] text-muted">{result.signals.length} checks</span>
        </div>
        <div className="flex flex-col gap-2.5">
          {result.signals.map((signal) => {
            const status = STATUS_META[signal.status];
            return (
              <div
                key={signal.key}
                className="rounded-card border border-line bg-card p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-pill border",
                        TONE_CLASS[status.tone].chip,
                      )}
                    >
                      <StatusGlyph status={signal.status} />
                    </span>
                    <span className="text-sm font-semibold">{signal.label}</span>
                  </div>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>
                <p className="mt-2.5 text-xs leading-relaxed text-muted">
                  {signal.detail}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {result.alternatives.length > 0 && (
        <Link href="/pharmacies" className="block">
          <div className="flex items-center gap-3 rounded-card border border-accent/30 bg-accent/10 p-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-pill bg-accent text-accent-ink">
              <StoreIcon className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">Find the real thing nearby</p>
              <p className="text-xs text-muted">
                {result.alternatives.length} verified pharmacies in range
              </p>
            </div>
            <ArrowRightIcon className="h-5 w-5 shrink-0 text-accent" />
          </div>
        </Link>
      )}

      {result.note && (
        <p className="rounded-card border border-line bg-surface p-4 text-xs leading-relaxed text-muted">
          {result.note}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <PillLink href="/scan" size="lg" className="w-full">
          Scan another
        </PillLink>
        <PillLink href="/" size="lg" variant="secondary" className="w-full">
          Done
        </PillLink>
      </div>
    </Screen>
  );
}
