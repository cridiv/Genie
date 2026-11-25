import type { Metadata } from "next";
import { LiveResultLoader } from "@/components/result/live-result-loader";
import { ResultView } from "@/components/result/result-view";
import {
  ABEOKUTA_FALLBACK_PHARMACIES,
  GENIE_AI_API_BASE,
  mapBackendPayloadToResult,
} from "@/lib/genie/api";
import { getResult, SCENARIO_VALUES } from "@/lib/genie/mock";
import type { Scenario, VerificationResult } from "@/lib/genie/types";
import { VERDICT_META } from "@/lib/genie/verdict";

export const instant = false;

function isScenario(value: string): value is Scenario {
  return (SCENARIO_VALUES as string[]).includes(value);
}

async function fetchServerScan(scanId: string): Promise<VerificationResult | null> {
  const base = (
    process.env.GENIE_AI_URL ||
    process.env.NEXT_PUBLIC_GENIE_AI_URL ||
    GENIE_AI_API_BASE
  ).replace(/\/+$/, "");
  try {
    const resp = await fetch(`${base}/v1/scans/${encodeURIComponent(scanId)}`, {
      cache: "no-store",
    });
    if (!resp.ok) return null;
    const raw = await resp.json();
    return mapBackendPayloadToResult(raw, ABEOKUTA_FALLBACK_PHARMACIES);
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ scenario: string }>;
}): Promise<Metadata> {
  const { scenario } = await params;
  if (isScenario(scenario)) {
    return { title: VERDICT_META[getResult(scenario).verdict].label };
  }
  return { title: `Scan ${scenario}` };
}

export default async function ResultPage({
  params,
}: {
  params: Promise<{ scenario: string }>;
}) {
  const { scenario } = await params;

  if (isScenario(scenario)) {
    return <ResultView result={getResult(scenario)} />;
  }

  const serverResult = await fetchServerScan(scenario);
  return <LiveResultLoader scanId={scenario} initialResult={serverResult} />;
}
