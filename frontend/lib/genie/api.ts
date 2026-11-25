import type {
  MatchedProduct,
  MatchedVersion,
  NearbyPharmaciesResponse,
  Pharmacy,
  RecentCheck,
  Scenario,
  SignalKey,
  SignalStatus,
  Verdict,
  VerificationResult,
  VerificationSignal,
} from "./types";

export const GENIE_AI_API_BASE = (
  process.env.NEXT_PUBLIC_GENIE_AI_URL || "http://102.209.46.116:8001"
).replace(/\/+$/, "");

export const ML_INFRA_API_BASE = (
  process.env.NEXT_PUBLIC_ML_INFRA_URL || "http://102.209.46.116:8000"
).replace(/\/+$/, "");

export const ABEOKUTA_DEFAULT_COORDS = {
  lat: 7.1475,
  lng: 3.3619,
  label: "Abeokuta, Ogun State",
};

/** Offline Abeokuta PCN-verified fallback if the API server is unreachable. */
export const ABEOKUTA_FALLBACK_PHARMACIES: Pharmacy[] = [
  {
    id: "ph_abk_vanguard",
    name: "Vanguard Pharmacy — Oke-Ilewo",
    address: "38 Lalubu Street (Beside Zenith Bank), Oke-Ilewo, Abeokuta",
    area: "Oke-Ilewo, Abeokuta",
    distanceKm: 2.8,
    licenseId: "PCN-OGN-VP-001",
    verified: true,
    stockConfirmed: false,
    latitude: 7.1419,
    longitude: 3.3372,
    googleMapsUrl:
      "https://www.google.com/maps/search/?api=1&query=Vanguard+Pharmacy+38+Lalubu+Street+Oke-Ilewo+Abeokuta",
    directionsUrl: "https://www.google.com/maps/dir/?api=1&destination=7.141900,3.337200",
  },
  {
    id: "ph_abk_medplus",
    name: "MedPlus Pharmacy — OOPL",
    address: "Opposite Olusegun Obasanjo Presidential Library, IBB Boulevard, Abeokuta",
    area: "IBB Boulevard, Abeokuta",
    distanceKm: 1.5,
    licenseId: "PCN-OGN-MP-002",
    verified: true,
    stockConfirmed: false,
    latitude: 7.1346,
    longitude: 3.3583,
    googleMapsUrl:
      "https://www.google.com/maps/search/?api=1&query=MedPlus+Pharmacy+OOPL+IBB+Boulevard+Abeokuta",
    directionsUrl: "https://www.google.com/maps/dir/?api=1&destination=7.134600,3.358300",
  },
  {
    id: "ph_abk_healthplus",
    name: "HealthPlus Pharmacy — IBB Boulevard",
    address: "Delta Mall (Shoprite), Ibrahim Babangida Boulevard, Abeokuta",
    area: "IBB Boulevard, Abeokuta",
    distanceKm: 1.4,
    licenseId: "PCN-OGN-HP-003",
    verified: true,
    stockConfirmed: false,
    latitude: 7.1361,
    longitude: 3.3562,
    googleMapsUrl:
      "https://www.google.com/maps/search/?api=1&query=HealthPlus+Pharmacy+Delta+Mall+Abeokuta",
    directionsUrl: "https://www.google.com/maps/dir/?api=1&destination=7.136100,3.356200",
  },
  {
    id: "ph_abk_goldcross",
    name: "Gold Cross Pharmacy — Idi-Aba",
    address: "15 Idi-Aba Road (Opposite Federal Medical Centre), Idi-Aba, Abeokuta",
    area: "Idi-Aba, Abeokuta",
    distanceKm: 2.0,
    licenseId: "PCN-OGN-GC-008",
    verified: true,
    stockConfirmed: false,
    latitude: 7.1472,
    longitude: 3.3801,
    googleMapsUrl:
      "https://www.google.com/maps/search/?api=1&query=Gold+Cross+Pharmacy+15+Idi-Aba+Road+Abeokuta",
    directionsUrl: "https://www.google.com/maps/dir/?api=1&destination=7.147200,3.380100",
  },
];

/* -------------------------------------------------------------------------- */
/*  Backend -> Frontend VerificationResult mapper                             */
/* -------------------------------------------------------------------------- */

function mapVerdict(raw: string | undefined): Verdict {
  switch (raw) {
    case "authentic":
      return "authentic";
    case "likely_authentic":
      return "likely_authentic";
    case "suspicious":
      return "suspicious";
    case "likely_counterfeit":
      return "likely_counterfeit";
    default:
      return "unknown";
  }
}

function mapScenario(verdict: Verdict): Scenario {
  if (verdict === "authentic" || verdict === "likely_authentic") return "authentic";
  if (verdict === "suspicious") return "suspicious";
  if (verdict === "likely_counterfeit") return "counterfeit";
  return "unknown";
}

function mapRegStatus(raw: string | undefined): MatchedProduct["registrationStatus"] {
  const lower = (raw || "").toLowerCase();
  if (lower.includes("active")) return "active";
  if (lower.includes("revok") || lower.includes("suspend") || lower.includes("cancel")) {
    return "revoked";
  }
  if (lower.includes("expir")) return "expired";
  return "unregistered";
}

const SIGNAL_MAP: Record<string, { key: SignalKey; label: string }> = {
  visual: { key: "visual", label: "Packaging visual" },
  nafdac: { key: "nafdac", label: "NAFDAC registry" },
  gtin: { key: "barcode", label: "Barcode & GTIN" },
  batch_expiry: { key: "batch_consistency", label: "Batch & expiry" },
  spec_ocr: { key: "version_match", label: "Printed specs (OCR)" },
  security_features: { key: "version_match", label: "Security features" },
  recalls_and_tells: { key: "nafdac", label: "Recall & alert check" },
};

function mapSignalStatus(sig: Record<string, unknown>): SignalStatus {
  if (sig.hard_negative) return "fail";
  if (sig.status !== "available") return "unknown";
  if (sig.direction === "positive") return "pass";
  if (sig.direction === "negative") return "warn";
  return "unknown";
}

export function mapBackendPayloadToResult(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  raw: any,
  alternatives: Pharmacy[] = ABEOKUTA_FALLBACK_PHARMACIES,
): VerificationResult {
  const payload = raw?.payload ?? raw;
  const verObj = payload?.verification ?? payload;
  const res = verObj?.result ?? payload?.result ?? {};

  const verdict = mapVerdict(res.verdict ?? raw?.verdict);
  const scanId = String(payload?.scan_id ?? raw?.scan_id ?? verObj?.scan_id ?? "scan_live");
  const mp = res.matched_product;

  const matchedProduct: MatchedProduct | null = mp
    ? {
        brandName: String(mp.brand_name || "Unknown product"),
        genericName: String(mp.generic_name || ""),
        strength: String(mp.strength || ""),
        form: String(mp.dosage_form || ""),
        manufacturer: String(mp.manufacturer || ""),
        nafdacNumber: String(mp.nafdac_number || ""),
        registrationStatus: mapRegStatus(mp.registration_status),
      }
    : null;

  const mv = res.matched_version;
  const matchedVersion: MatchedVersion | null = mv
    ? {
        label: String(mv.edition_id || mv.summary || "Primary edition"),
        effectiveFrom: mv.is_historical_version ? "Legacy edition" : "Current edition",
        isCurrent: !mv.is_historical_version,
      }
    : null;

  const rawSignals: Array<Record<string, unknown>> = Array.isArray(res.signals)
    ? res.signals
    : [];

  const signals: VerificationSignal[] = rawSignals
    .filter((s) => s.status === "available" || Boolean(s.hard_negative) || s.name === "visual")
    .map((s) => {
      const name = String(s.name || "visual");
      const meta = SIGNAL_MAP[name] ?? { key: "version_match" as SignalKey, label: name };
      return {
        key: meta.key,
        label: meta.label,
        status: mapSignalStatus(s),
        detail: String(s.summary || s.limitation || "Checked"),
      };
    });

  const limitations: string[] = Array.isArray(res.limitations)
    ? res.limitations.map(String)
    : Array.isArray(raw?.limitations)
      ? raw.limitations.map(String)
      : [];

  const summary = String(res.summary || raw?.summary || "");
  const noteParts = [summary, ...limitations].filter(Boolean);

  return {
    id: scanId,
    scenario: mapScenario(verdict),
    verdict,
    confidence: Number(res.confidence ?? raw?.confidence ?? 0),
    scannedAt: raw?.created_at ? formatRelativeTime(String(raw.created_at)) : "Just now",
    matchedProduct,
    matchedVersion,
    signals,
    alternatives,
    discoveryJobId: verObj?.discovery_job_id || raw?.discovery_job_id || undefined,
    note: noteParts.join(" · ") || undefined,
  };
}

export function formatRelativeTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "Recently";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return "Just now";
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

/* -------------------------------------------------------------------------- */
/*  Session cache for immediate navigation from /scan -> /result/<scan_id>    */
/* -------------------------------------------------------------------------- */

const RESULT_STORAGE_PREFIX = "genie_live_result:";

export function rememberLiveResult(result: VerificationResult): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      `${RESULT_STORAGE_PREFIX}${result.id}`,
      JSON.stringify(result),
    );
  } catch {
    // Ignore storage quota errors
  }
}

export function loadLiveResult(scanId: string): VerificationResult | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(`${RESULT_STORAGE_PREFIX}${scanId}`);
    return raw ? (JSON.parse(raw) as VerificationResult) : null;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/*  Live API calls (via Next.js server-side proxy routes)                     */
/* -------------------------------------------------------------------------- */

export async function verifyCapturedImage(dataUrl: string): Promise<VerificationResult> {
  const blobResp = await fetch(dataUrl);
  const blob = await blobResp.blob();
  const form = new FormData();
  form.append("file", blob, "scan.jpg");

  const resp = await fetch("/api/verify/image?compare_visual=true&auto_discover=true", {
    method: "POST",
    body: form,
  });
  if (!resp.ok) {
    const errBody = await resp.text();
    throw new Error(`Verification failed (${resp.status}): ${errBody.slice(0, 160)}`);
  }
  const raw = await resp.json();

  let alts = ABEOKUTA_FALLBACK_PHARMACIES;
  try {
    const ph = await fetchNearbyPharmacies({
      lat: ABEOKUTA_DEFAULT_COORDS.lat,
      lng: ABEOKUTA_DEFAULT_COORDS.lng,
      limit: 4,
      verifiedOnly: true,
    });
    if (ph.pharmacies.length > 0) alts = ph.pharmacies;
  } catch {
    // Keep Abeokuta fallback
  }

  const mapped = mapBackendPayloadToResult(raw, alts);
  rememberLiveResult(mapped);
  return mapped;
}

export async function fetchScanById(scanId: string): Promise<VerificationResult | null> {
  const resp = await fetch(`/api/scans/${encodeURIComponent(scanId)}`, {
    cache: "no-store",
  });
  if (!resp.ok) return null;
  const raw = await resp.json();
  return mapBackendPayloadToResult(raw, ABEOKUTA_FALLBACK_PHARMACIES);
}

export async function fetchRecentScans(limit = 25): Promise<RecentCheck[]> {
  const resp = await fetch(`/api/scans?limit=${limit}`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`Failed to fetch scan history (${resp.status})`);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rows: any[] = await resp.json();
  return rows.map((row) => {
    const verdict = mapVerdict(row.verdict);
    return {
      id: String(row.scan_id),
      scenario: mapScenario(verdict),
      productName: String(row.product_name || row.nafdac_number || "Scanned medicine"),
      verdict,
      when: row.created_at ? formatRelativeTime(String(row.created_at)) : "Recently",
    };
  });
}

export async function fetchNearbyPharmacies(params: {
  lat?: number;
  lng?: number;
  location?: string;
  radiusKm?: number;
  limit?: number;
  verifiedOnly?: boolean;
}): Promise<NearbyPharmaciesResponse> {
  const qs = new URLSearchParams();
  if (params.lat !== undefined && params.lng !== undefined) {
    qs.set("lat", String(params.lat));
    qs.set("lng", String(params.lng));
  }
  if (params.location) qs.set("location", params.location);
  if (params.radiusKm) qs.set("radius_km", String(params.radiusKm));
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.verifiedOnly) qs.set("verified_only", "true");

  const resp = await fetch(`/api/pharmacies/nearby?${qs.toString()}`, {
    cache: "no-store",
  });
  if (!resp.ok) {
    throw new Error(`Nearby pharmacies API failed (${resp.status})`);
  }
  return (await resp.json()) as NearbyPharmaciesResponse;
}
