import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ResultView } from "@/components/result/result-view";
import { getResult, SCENARIO_VALUES } from "@/lib/genie/mock";
import type { Scenario } from "@/lib/genie/types";
import { VERDICT_META } from "@/lib/genie/verdict";

function isScenario(value: string): value is Scenario {
  return (SCENARIO_VALUES as string[]).includes(value);
}

// The entire page is derived from the route param, so this segment is allowed
// to block the navigation instead of splitting into a Suspense boundary that
// would only ever show a fallback.
export const instant = false;

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

export default async function ResultPage({
  params,
}: {
  params: Promise<{ scenario: string }>;
}) {
  const { scenario } = await params;
  if (!isScenario(scenario)) notFound();

  return <ResultView result={getResult(scenario)} />;
}
