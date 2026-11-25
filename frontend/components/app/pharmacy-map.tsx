import { cn } from "@/lib/cn";
import type { Pharmacy } from "@/lib/genie/types";

interface PharmacyMapProps {
  pharmacies?: Pharmacy[];
  userLat?: number;
  userLng?: number;
}

export function PharmacyMap({
  pharmacies = [],
  userLat = 7.1475,
  userLng = 3.3619,
}: PharmacyMapProps) {
  const withCoords = pharmacies.filter(
    (p) => typeof p.latitude === "number" && typeof p.longitude === "number",
  );

  // Project lat/lng deltas around the user's center (50%, 44%) into percentage coordinates
  const maxDelta = Math.max(
    0.015,
    ...withCoords.map((p) =>
      Math.max(
        Math.abs((p.latitude ?? userLat) - userLat),
        Math.abs((p.longitude ?? userLng) - userLng),
      ),
    ),
  );

  const pins = withCoords.slice(0, 12).map((p) => {
    const dx = ((p.longitude ?? userLng) - userLng) / maxDelta;
    const dy = -((p.latitude ?? userLat) - userLat) / maxDelta;
    const x = Math.max(10, Math.min(90, 50 + dx * 36));
    const y = Math.max(14, Math.min(76, 44 + dy * 28));
    return {
      id: p.id,
      name: p.name,
      verified: p.verified,
      x,
      y,
      href:
        p.googleMapsUrl ||
        p.directionsUrl ||
        `https://www.google.com/maps/search/?api=1&query=${p.latitude},${p.longitude}`,
    };
  });

  const furthestKm =
    pharmacies.length > 0
      ? Math.max(...pharmacies.map((p) => p.distanceKm)).toFixed(1)
      : "5.0";

  return (
    <div className="relative aspect-[16/11] w-full overflow-hidden rounded-card border border-line bg-surface">
      <svg
        viewBox="0 0 100 70"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden
      >
        <g stroke="var(--color-line)" strokeWidth="0.7" strokeLinecap="round">
          <path d="M0 20H100" />
          <path d="M0 48H100" />
          <path d="M22 0V70" />
          <path d="M55 0V70" />
          <path d="M82 0V70" />
          <path d="M0 64L100 24" />
        </g>
        <g fill="var(--color-card)">
          <rect x="4" y="24" width="14" height="18" rx="2.5" />
          <rect x="27" y="24" width="23" height="9" rx="2.5" />
          <rect x="60" y="26" width="17" height="16" rx="2.5" />
          <rect x="5" y="52" width="12" height="9" rx="2.5" />
          <rect x="28" y="52" width="20" height="9" rx="2.5" />
          <rect x="60" y="52" width="17" height="10" rx="2.5" />
          <rect x="86" y="30" width="10" height="14" rx="2.5" />
        </g>
      </svg>

      {/* You are here */}
      <div className="absolute" style={{ left: "50%", top: "44%" }} title="Your location">
        <span className="animate-ping-slow absolute -inset-3 rounded-pill bg-accent" />
        <span className="relative block h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-accent ring-2 ring-ink" />
      </div>

      {pins.map((pin) => (
        <a
          key={pin.id}
          href={pin.href}
          target="_blank"
          rel="noopener noreferrer"
          title={`Open ${pin.name} in Google Maps`}
          className={cn(
            "absolute flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-pill border-2 border-ink transition hover:scale-110",
            pin.verified ? "bg-accent text-accent-ink" : "bg-bad text-white",
          )}
          style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
        >
          <span className="h-1.5 w-1.5 rounded-pill bg-current" />
        </a>
      ))}

      <div className="absolute inset-x-3 bottom-3 flex items-center gap-3 rounded-pill border border-line bg-ink px-3 py-1.5 text-[10px] font-semibold text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-pill bg-accent" /> verified
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-pill bg-bad" /> unverified
        </span>
        <span className="ml-auto">up to {furthestKm} km</span>
      </div>
    </div>
  );
}
