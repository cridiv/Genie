"use client";

import { useCallback, useEffect, useState } from "react";
import { AppHeader } from "@/components/app/app-header";
import { PharmacyMap } from "@/components/app/pharmacy-map";
import { Screen } from "@/components/app/screen";
import { Badge } from "@/components/ui/badge";
import { ArrowRightIcon, InfoIcon, PinIcon } from "@/components/ui/icons";
import { PillButton } from "@/components/ui/pill";
import { cn } from "@/lib/cn";
import {
  ABEOKUTA_DEFAULT_COORDS,
  ABEOKUTA_FALLBACK_PHARMACIES,
  fetchNearbyPharmacies,
} from "@/lib/genie/api";
import type { Pharmacy } from "@/lib/genie/types";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "verified", label: "Verified" },
  { id: "stock", label: "In stock" },
] as const;

type FilterId = (typeof FILTERS)[number]["id"];

export default function PharmaciesPage() {
  const [filter, setFilter] = useState<FilterId>("all");
  const [pharmacies, setPharmacies] = useState<Pharmacy[]>(ABEOKUTA_FALLBACK_PHARMACIES);
  const [coords, setCoords] = useState<{ lat: number; lng: number }>({
    lat: ABEOKUTA_DEFAULT_COORDS.lat,
    lng: ABEOKUTA_DEFAULT_COORDS.lng,
  });
  const [locationLabel, setLocationLabel] = useState<string>(
    `Near ${ABEOKUTA_DEFAULT_COORDS.label}`,
  );
  const [loading, setLoading] = useState<boolean>(true);
  const [usingGps, setUsingGps] = useState<boolean>(false);

  const loadPharmacies = useCallback(
    async (lat: number, lng: number, label: string) => {
      setLoading(true);
      setCoords({ lat, lng });
      setLocationLabel(label);
      try {
        const data = await fetchNearbyPharmacies({
          lat,
          lng,
          location: label,
          radiusKm: 20,
          limit: 12,
        });
        if (data.pharmacies.length > 0) {
          setPharmacies(data.pharmacies);
        }
      } catch {
        // Keep Abeokuta PCN-verified fallback if backend is unreachable
        setPharmacies(ABEOKUTA_FALLBACK_PHARMACIES);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const locateUser = useCallback(() => {
    if (typeof window === "undefined" || !("geolocation" in navigator)) {
      void loadPharmacies(
        ABEOKUTA_DEFAULT_COORDS.lat,
        ABEOKUTA_DEFAULT_COORDS.lng,
        `Near ${ABEOKUTA_DEFAULT_COORDS.label}`,
      );
      return;
    }

    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUsingGps(true);
        void loadPharmacies(
          pos.coords.latitude,
          pos.coords.longitude,
          "Near your current location",
        );
      },
      () => {
        setUsingGps(false);
        void loadPharmacies(
          ABEOKUTA_DEFAULT_COORDS.lat,
          ABEOKUTA_DEFAULT_COORDS.lng,
          `Near ${ABEOKUTA_DEFAULT_COORDS.label}`,
        );
      },
      { enableHighAccuracy: true, timeout: 6000, maximumAge: 60000 },
    );
  }, [loadPharmacies]);

  useEffect(() => {
    locateUser();
  }, [locateUser]);

  const list = pharmacies.filter((pharmacy) => {
    if (filter === "verified") return pharmacy.verified;
    if (filter === "stock") return pharmacy.stockConfirmed;
    return true;
  });

  return (
    <Screen>
      <AppHeader
        title="Verified pharmacies"
        subtitle={loading ? "Finding PCN pharmacies nearby…" : locationLabel}
      />

      <PharmacyMap
        pharmacies={list}
        userLat={coords.lat}
        userLng={coords.lng}
      />

      <div className="flex flex-wrap items-center gap-2">
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

        <button
          type="button"
          onClick={locateUser}
          className="ml-auto h-9 rounded-pill border border-line bg-surface px-3 text-xs font-semibold text-fg transition active:scale-95"
        >
          {usingGps ? "Refresh GPS" : "Use my location"}
        </button>
      </div>

      <div className="flex flex-col gap-2.5">
        {list.length === 0 ? (
          <div className="rounded-card border border-line bg-card p-4 text-xs text-muted">
            No pharmacies match this filter yet.
          </div>
        ) : (
          list.map((pharmacy) => {
            const directionsHref =
              pharmacy.directionsUrl ||
              pharmacy.googleMapsUrl ||
              `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                `${pharmacy.name}, ${pharmacy.address}`,
              )}`;
            return (
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
                        {pharmacy.verified ? "PCN Verified" : "Unverified"}
                      </Badge>
                      <Badge tone={pharmacy.stockConfirmed ? "accent" : "muted"} dot>
                        {pharmacy.stockConfirmed ? "Stock confirmed" : "Stock unconfirmed"}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3">
                  <span className="truncate font-mono text-[11px] text-muted">
                    {pharmacy.licenseId}
                  </span>
                  <a
                    href={directionsHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="shrink-0"
                  >
                    <PillButton
                      size="sm"
                      variant="secondary"
                      className="h-8 px-3 text-xs"
                    >
                      Directions <ArrowRightIcon className="h-3.5 w-3.5" />
                    </PillButton>
                  </a>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="flex items-start gap-2.5 rounded-card border border-line bg-surface p-4">
        <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-info" />
        <p className="text-[11px] leading-relaxed text-muted">
          <span className="font-semibold text-fg">License is not stock.</span>{" "}
          PCN Verified means the pharmacy is licensed and checked in Ogun State /
          Nigeria. Stock confirmed means the product was recently seen available
          there.
        </p>
      </div>
    </Screen>
  );
}
