# GENIE AI — Next Phase Build Plan: Curated Trust, Non-NAFDAC Intelligence & Graceful Degradation

> **Principle:** NAFDAC data can disqualify a product but can never, on its own, confirm one. A missing signal never counts as a negative; a negative signal always counts. Positive confidence is capped by what we could actually check.

---

### Phase A — Curated `trusted_sources` Registry & Allowlisted Visual Harvesting
**Goal:** Replace open-web image guessing with an auditable Nigerian allowlist so reference images only come from vetted pharmacies and official manufacturers (open web search stays active for recalls and counterfeit intel).

- **New file:** `registry/trusted_sources.py` (backed by a new `data/genie.db` SQLite database; `data/greenbook.db` stays purely the NAFDAC mirror)
  - Table `trusted_sources(domain PRIMARY KEY, name, source_type ['pharmacy'|'manufacturer'|'regulator'], country, trust_status ['verified'|'provisional'], verified_by, verified_on, criteria_met JSON, license_ref, notes, is_active)`.
  - Documented verification criteria rubric: `pcn_premises_licensed`, `physical_address_verified`, `superintendent_pharmacist_named`, `official_brand_domain`, `regulatory_authority`.
  - **Only `trust_status='verified'` sources may supply reference images.** Seed entries whose criteria have not been checked (e.g. `gomed.ng`, `medecify.com`) are inserted as `provisional` with empty `criteria_met`, so the demo can always say exactly how a source got on the list.
  - Default seed: manufacturers (`gsk.com`, `novartis.com`, `emzor.com`, `fidson.com`, …) as `official_brand_domain`; Nigerian pharmacies (`medplusnigeria.com`, `healthplusnigeria.com`, `drugstoc.com`, `onehealthng.com`, `advantagehealthafrica.com`, `gomed.ng`, `medecify.com`, …) as `provisional` until criteria are recorded.
  - CLI `scripts/trusted_sources.py`: `init`, `list`, `add`, `verify <domain> --criteria ... --by ...`, `deactivate`.
- **Updates to discovery & image curation:**
  - `discovery/trust.py`: add B2B marketplaces (`indiamart.com`, `alibaba.com`, `made-in-china.com`, `tradeindia.com`) to `BLOCKED_DOMAINS`.
  - `discovery/planner.py`: add `build_trusted_image_queries(...)` — `site:`-scoped Serper image queries over verified trusted domains + the product's manufacturer, **capped at ~5 domains per query** (split into multiple queries if needed).
  - `intelligence/images.py`: add `trusted_only: bool = True` to `collect_candidate_image_urls(...)`; only active `verified` trusted domains are eligible as packaging reference candidates.
  - `intelligence/schemas.py`: record `captured_from_domain`, `captured_from_type`, `captured_at` (ISO UTC fetch date), and `market_verified` on `VerifiedReferenceImage` (a trusted pharmacy can still show an old or export photo).
- **Promote CLI (built early, not deferred):** `scripts/promote_reference.py <product_slug> <image_id>` moves a reference image `staging` → `approved` with `approved_by` / `approved_at`, so demo products can legitimately reach Level A/B.

---

### Phase B — Non-NAFDAC Product Intelligence & SmPC Spec Extraction
**Goal:** Extract high-value signals the Greenbook does *not* publish, plus structured SmPC specs needed for deterministic OCR and batch checks.

- **SmPC section pre-extraction (fixes truncation bug):** `build_dossier_prompt` truncates each source at 4,000 chars, which drops SmPC §6.3 *Shelf life* and §6.4 *Storage* (near the end of the PDF). Add a deterministic regex extractor that pulls §4.x/§6.3/§6.4/§6.5 blocks from SmPC text and passes them as a dedicated prompt section before truncation.
- **Update `intelligence/schemas.py`** (`ExtractedDossierResponse` + `CandidateProductDossier`):
  - `gtins: List[str]` — GS1 Mod-10 validated, merged deterministically from scraped JSON-LD / trusted pages.
  - `shelf_life_months: Optional[int]`, `storage_statement: Optional[str]` — verbatim from SmPC.
  - `expected_security_features: List[SecurityFeatureSpec]` — `{feature_type: 'scratch_pin'|'hologram'|'tamper_seal'|'tablet_debossing'|'qr_code'|'braille', description, required, verifiable: bool, source_url, verbatim_quote}`. `verifiable=true` only for features that can be checked against an external authority (scratch PIN that validates, QR resolving to the manufacturer's domain).
    - ⚠️ Before relying on MAS/Sproxil scratch PINs, confirm the scheme is still current in NAFDAC policy.
  - `known_counterfeit_tells: List[CounterfeitTell]` — `{tell_type: 'compromised_batch'|'packaging_defect'|'spelling_error'|'wrong_color_or_foil'|'missing_security_feature'|'fake_manufacturer_info', summary, affected_batches, fake_indicator, genuine_indicator, alert_ref, source_url, verbatim_quote, source_kind: 'nafdac_derived'|'independent'}` (tells from NAFDAC alerts are tagged `nafdac_derived`).
  - `reference_level: Literal["A", "B", "C"]` — computed **only from `approved` images** (staging images never count):
    - **A:** ≥2 distinct approved views (e.g. front + back/blister) from verified trusted sources.
    - **B:** exactly one approved view (usually front).
    - **C:** no approved packaging reference (degraded mode — the expected default for most products).
- **Update `intelligence/synthesizer.py`:** extend `DOSSIER_SYSTEM_INSTRUCTION` to extract `shelf_life_months`, `storage_statement`, `expected_security_features`, `known_counterfeit_tells` (mining `regulatory_alerts` / `packaging_alerts` sources for seizure details, compromised batches, fake defects); attach validated `gtins` from `bundle.sources`; compute `reference_level` after `group_packaging_versions(...)`.

---

### Phase D — Multi-Signal Verification Engine & Graceful Degradation (`verification/`)
**Goal:** Coverage-based asymmetric scorer with the `nafdac_derived` vs `independent` ceiling enforced in code. Reads existing `data/products/<slug>/product.json` dossiers directly (no dependency on Phase C's store).

- **`verification/schemas.py`:**
  - `ScanInput`: `product_name_hint`, `nafdac_number`, `gtin`, `batch_number`, `mfg_date`, `expiry_date`, `ocr_text`, `ocr_confidence`, `observed_security_features`, `features_checked` (features the user was explicitly prompted to show), `verified_features` (e.g. PIN validated), optional `visual_match` from CV adapter.
  - `SignalResult`: `name`, `source: 'nafdac_derived'|'independent'`, `status: 'available'|'unavailable'|'not_applicable'`, `direction: 'positive'|'negative'|'neutral'`, `strength: 0..1`, `hard_negative: None|'suspicious'|'likely_counterfeit'`, `weight`, `summary`, `evidence`.
  - `VerificationVerdict`: `authentic` | `likely_authentic` | `registered_unverified` | `suspicious` | `likely_counterfeit` | `unknown`.
  - `VerificationResult`: `verdict`, `confidence`, `coverage`, `reference_level`, `matched_product`, `matched_version`, `signals[]`, `limitations[]`, `counterfeit_tell_hits[]`.
  - `to_ml_infra_verdict()` mapping helper → `Consistent with genuine` / `Suspicious` / `Cannot verify` (for later alignment with `ml_infra/`).
- **Signals (`verification/signals/`) with default weights (scoring signals sum to `1.00`; `recalls_and_tells` is a `0.00`-weight hard-negative safety gate so clear checks never dilute positive scores):**

| Signal | Source | Weight | Positive when | Hard negative |
| --- | --- | --- | --- | --- |
| `visual.py` | independent | **0.40** *(always applicable; A = 0.40, B = 0.30, C = unavailable)* | CV match vs current **or historical** approved versions (`MockCVAdapter` for tests/demo) | severe anomaly at level A/B → `suspicious` |
| `nafdac.py` | nafdac_derived | **0.20** | registered, status active/renewal, product + manufacturer match | invented / revoked / belongs to another product → `likely_counterfeit`; expired registration → `suspicious` |
| `spec_ocr.py` | nafdac_derived | **0.15** | strength / form / pack / manufacturer match | only confident mismatch (`ocr_confidence ≥ 0.85` and unambiguous) → `suspicious` |
| `batch_expiry.py` | nafdac_derived | **0.10** | dates plausible vs SmPC shelf life | inverted dates / impossible gap → `suspicious`; expired pack → `suspicious` |
| `gtin.py` | independent | **0.08** *(`not_applicable` if dossier has no GTINs)* | check digit valid + linked to this product (weak, max strength 0.4) | invalid check digit or GTIN of another product → `likely_counterfeit` |
| `security_features.py` | independent | **0.07** *(`not_applicable` if dossier has none)* | strong only for `verified_features`; presence alone = weak (max 0.3) | only if feature was in `features_checked` and still absent → `suspicious` ("not observed" ≠ "absent") |
| `recalls_and_tells.py` | per tell `source_kind` | **0.00 (Gate)** | never (clear = neutral; does not penalize score) | batch / tell match → `likely_counterfeit` at any coverage |

- **Registration status mapping (`nafdac.py`):** `Active` → active; `Ongoing Renewal` / `Renewal in progress` → active-with-note (never a negative); `Expired` → `suspicious` (could be older legal stock); `Revoked` / `Cancelled` / `Suspended` → `likely_counterfeit`; unknown string → neutral + limitation.
- **Core scorer (`verification/engine.py`):**
  1. Resolve product from `product.json` dossiers + `GreenbookStore`. Not in Greenbook at all → explicit `unregistered_product` finding, verdict `suspicious`, recommend discovery.
  2. `coverage = sum(weights of available signals) / sum(weights of applicable signals)`.
  3. **Hard negatives (any coverage):** worst hard negative wins (`likely_counterfeit` > `suspicious`).
  4. Weighted score over available signals only; missing signals never count against the pack.
  5. **Positive ceilings:**
     - `authentic` → `reference_level ∈ {A, B}` + positive visual + `coverage ≥ 0.65`.
     - `likely_authentic` → positive visual (level B or reduced coverage) **or** a positive `verified_features` signal; never from nafdac_derived signals alone, never from GTIN alone, never from "no recall hit".
     - `registered_unverified` → registration/spec/batch/GTIN clean, but no independent visual or verified-feature confirmation ("Registered & spec-consistent — packaging not independently verified").
     - `unknown` → `coverage < 0.30` or product unresolved.
  6. Auto-populate `limitations[]` for every unavailable signal (e.g. "No verified reference image for this product — packaging was not visually compared").

---

### Phase E — Verification CLI, Offline Tests & Pitch Sync
- **Demo CLI (`scripts/run_verify.py`)** against saved dossiers (Augmentin `04-1928`, Coartem `04-3275`):
  1. Genuine Level A/B scan → `authentic`
  2. Legitimate historical edition → recognised, no false alarm
  3. Level C scan (valid NAFDAC + OCR + shelf life, no reference photo) → `registered_unverified` + `limitations[]`
  4. Coartem with `Ongoing Renewal` status → not penalised
  5. Cloned NAFDAC + recalled batch (`562626`) or impossible shelf-life gap → `likely_counterfeit` / `suspicious` even at Level C
  6. Unregistered drug → `unregistered_product` + recommend discovery
- **Offline unit tests:** `tests/test_trusted_sources.py`, `tests/test_verification_engine.py` (every ceiling rule, hard-negative mapping, status mapping, "not observed ≠ absent", OCR-confidence gate), plus SmPC section extractor tests.
- **Docs sync:** update `PITCH_DECK_GUIDE.md` (Slides 3, 5, 8 + Q&A: "our verdict degrades by coverage, never by guesswork") and `TECHNICAL_DECISIONS.md`.

---

### Phase C — Deterministic Evidence Gate & Versioned Product Store *(after the engine)*
- **`validation/evidence.py`:** verbatim quote verifier (whitespace + curly/straight quote normalised; Greenbook claims checked against our formatted record text, e.g. `"Product Name: Augmentin 625 mg"`); numeric grounding (`nafdac_number`, `gtins`, `strength`, `pack_size`, `shelf_life_months`, `affected_batches`); Tier 1 vs Tier 2/3 conflict detection; promotion rules (text dossier auto-promotes only when Tier 1 anchored + all numeric claims grounded + no Tier 1 conflict; images per Phase A promote rules).
- **`registry/product_store.py`:** SQLite persistence in `data/genie.db` for `products`, append-only `packaging_versions`, `expected_security_features`, `known_counterfeit_tells`, with `product.json` export kept. Engine switches from JSON files to the store once this lands.

---

### Out of Scope for the Hackathon (documented, not built)
- Continuous monitoring / freshness re-checks (Greenbook mirror lags on recalls and status changes).
- Manufacturer brand-asset (logo/colour) check and price-band signal (dropped: fragile under phone lighting / volatile Nigerian pricing).
- Schema alignment with `ml_infra/` (use `to_ml_infra_verdict()` mapping until then).

---

### Recommended Build Order
1. **Build 1 (Phases A + B):** trusted_sources registry + promote CLI + allowlisted image harvesting + SmPC section extraction + enriched dossier → re-test live on Augmentin & Coartem.
2. **Build 2 (Phases D + E):** verification engine over `product.json` + demo CLI + tests + pitch sync (demo centrepiece).
3. **Build 3 (Phase C):** evidence gate + SQLite product store.
