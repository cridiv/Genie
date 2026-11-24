"use client";

import { useState } from "react";
import { AppHeader } from "@/components/app/app-header";
import { PharmacyMap } from "@/components/app/pharmacy-map";
import { Screen } from "@/components/app/screen";
import { Badge } from "@/components/ui/badge";
import { ArrowRightIcon, InfoIcon, PinIcon } from "@/components/ui/icons";
import { PillButton } from "@/components/ui/pill";
import { cn } from "@/lib/cn";
import { PHARMACIES } from "@/lib/genie/mock";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "verified", label: "Verified" },
  { id: "stock", label: "In stock" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

export default function PharmaciesPage() {
  const [filter, setFilter] = useState<FilterId>("all");

  const list = PHARMACIES.filter((pharmacy) => {
    if (filter === "verified") return pharmacy.verified;
    if (filter === "stock") return pharmacy.stockConfirmed;
    return true;
  });

  return (
    <Screen>
      <AppHeader
        title="Verified pharmacies"
        subtitle="Near Victoria Island, Lagos"
      />

      <PharmacyMap />

      <div className="flex gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => setFilter(option.id)}
            className={cn(
              "h-9 rounded-pill border px-4 text-sm font-semibold transition active:scale-95",
              filter === option.id
                ? "border-accent bg-accent text-accent-ink"
                : "border-line bg-card text-muted",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2.5">
        {list.map((pharmacy) => (
          <div
            key={pharmacy.id}
            className="rounded-card border border-line bg-card p-4"
          >
            <div className="flex items-start gap-3">
              <span
                className={cn(
                  "flex h-11 w-11 shrink-0 items-center justify-center rounded-pill",
                  pharmacy.verified
                    ? "bg-accent text-accent-ink"
                    : "border border-line bg-surface text-muted",
                )}
              >
                <PinIcon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="truncate text-sm font-bold">{pharmacy.name}</h2>
                  <span className="shrink-0 text-xs font-semibold text-muted">
                    {pharmacy.distanceKm.toFixed(1)} km
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {pharmacy.address} · {pharmacy.area}
                </p>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <Badge tone={pharmacy.verified ? "ok" : "muted"} dot>
                    {pharmacy.verified ? "Verified" : "Unverified"}
                  </Badge>
                  <Badge tone={pharmacy.stockConfirmed ? "accent" : "muted"} dot>
                    {pharmacy.stockConfirmed ? "Stock confirmed" : "Stock unconfirmed"}
                  </Badge>
                </div>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3">
              <span className="font-mono text-[11px] text-muted">
                {pharmacy.licenseId}
              </span>
              <PillButton
                size="sm"
                variant="secondary"
                className="h-8 px-3 text-xs"
              >
                Directions <ArrowRightIcon className="h-3.5 w-3.5" />
              </PillButton>
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-start gap-2.5 rounded-card border border-line bg-surface p-4">
        <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-info" />
        <p className="text-[11px] leading-relaxed text-muted">
          <span className="font-semibold text-fg">License is not stock.</span>{" "}
          Verified means the pharmacy is licensed and checked. Stock confirmed
          means the product was recently seen available there.
        </p>
      </div>
    </Screen>
  );
}
