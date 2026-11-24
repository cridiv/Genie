import { cn } from "@/lib/cn";

const PINS = [
  { id: "ph_1", x: 26, y: 34, verified: true },
  { id: "ph_2", x: 64, y: 22, verified: true },
  { id: "ph_3", x: 78, y: 58, verified: true },
  { id: "ph_4", x: 40, y: 74, verified: false },
  { id: "ph_5", x: 18, y: 62, verified: true },
];

export function PharmacyMap() {
  return (
    <div className="relative aspect-[16/11] w-full overflow-hidden rounded-card border border-line bg-surface">
      <svg
        viewBox="0 0 100 70"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
        aria-hidden
      >
        <g
          stroke="var(--color-line)"
          strokeWidth="0.7"
          strokeLinecap="round"
        >
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
      <div className="absolute" style={{ left: "50%", top: "44%" }}>
        <span className="animate-ping-slow absolute -inset-3 rounded-pill bg-accent" />
        <span className="relative block h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-pill bg-accent ring-2 ring-ink" />
      </div>

      {PINS.map((pin) => (
        <span
          key={pin.id}
          className={cn(
            "absolute flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-pill border-2 border-ink",
            pin.verified ? "bg-accent text-accent-ink" : "bg-bad text-white",
          )}
          style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
        >
          <span className="h-1.5 w-1.5 rounded-pill bg-current" />
        </span>
      ))}

      <div className="absolute inset-x-3 bottom-3 flex items-center gap-3 rounded-pill border border-line bg-ink px-3 py-1.5 text-[10px] font-semibold text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-pill bg-accent" /> verified
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-pill bg-bad" /> unverified
        </span>
        <span className="ml-auto">3.2 km</span>
      </div>
    </div>
  );
}
