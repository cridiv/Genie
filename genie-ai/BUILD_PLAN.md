# GENIE AI — Build Plan

> End-to-end build plan for **GENIE AI** (everything outside **Genium** and the **Computer Vision model**), scoped for **pharmaceuticals / drugs v1** and structured to be built cleanly ahead of a short hackathon.

---

## 1. Tech Stack & Key Decisions

| Area | Choice | Why |
| --- | --- | --- |
| **Language & API** | **Pure Python 3.12+**, **FastAPI**, **Pydantic v2** | Zero cross-language glue with forked `searchify` modules and the Python CV model. Strict typing + Pydantic gives TypeScript-level cleanliness, plus auto-generated OpenAPI/Swagger docs to hand directly to the Genium team. |
| **Database** | **PostgreSQL** (+ `SQLAlchemy 2.0` async + `Alembic`), with SQLite fallback for local tests | Relational integrity for product versions, evidence claims, and geospatial pharmacy queries (`PostGIS` or simple Haversine SQL for hackathon speed). |
| **Web Acquisition** | **Forked lean subset of `searchify`** (no `rerank`, no `mcp`, no `cli`) | Keeps search, multi-stage extraction, SSRF protection, PDF parsing, and JSON-LD `Product` parsing without the ~1–2 GB RAM local cross-encoder. |
| **AI Extraction** | **Cloud LLM API** (provider-agnostic adapter: Gemini / OpenAI / Anthropic) with strict structured JSON outputs | Rules + JSON-LD run first (zero LLM cost); LLM only runs on unstructured text/PDFs to extract drug specs, packaging cues, and claims. |
| **Background Jobs** | Lightweight async job runner (FastAPI `BackgroundTasks` + DB job table for v1; easy swap to `ARQ`/Redis later) | Keeps hackathon deployment to 1 API container + 1 DB instead of managing extra broker infra. |
| **External Boundaries** | **Mockable CV Adapter** + versioned **Genium REST API** | Lets you build, test, and demo Genie completely independently until the CV model and Genium app plug in. |

---

## 2. What We Fork from `searchify` (and What We Drop)

**Keep & adapt into `genie/acquisition/`:**
- `search/`: `duckduckgo.py`, `searxng.py`, `cloud.py` (optional Serper/Tavily fallback), `_common.py`, `regions.py`
- `extract/`: `pages.py`, `reader.py`, `htmltext.py`, `pdf.py`, `netlimits.py`, `egress.py`, `reasons.py`, `structured.py`
  - **Extend `structured.py`** to also capture:
    - `Product.image`, `og:image`, and high-res packaging `<img>` candidates (needed for CV reference sets & versioning)
    - `manufacturer`, `mpn`, and regex hits for **NAFDAC registration numbers** (e.g., `A4-XXXX`, `B4-XXXX`, `04-XXXX`)
- **Evidence pattern from `skill/references/sources.py`** → adapt into `genie/validation/evidence.py`:
  - Verbatim quote verification against fetched page text
  - Numeric claim verification (ensures extracted NAFDAC IDs, GTINs, dosages, and pack sizes appear in cited source text)
  - Live URL + quote re-check for continuous monitoring

**Drop:**
- `rerank.py` (removes `sentence-transformers` and 1–2 GB RAM overhead)
- `mcp_server.py`, `cli.py`, `interview.py`, `profile.py`, `bench/`

---

## 3. Repository Structure

```text
genie/
├── app/
│   ├── main.py                  # FastAPI entrypoint, OpenAPI docs, healthcheck
│   ├── config.py                # Env settings (DB, LLM key, search backend, CV URL)
│   ├── api/
│   │   ├── verify.py            # POST /v1/verify (main Genium scan endpoint)
│   │   ├── products.py          # Product & version lookup, staging review endpoints
│   │   ├── discovery.py         # Trigger/poll unknown product discovery jobs
│   │   ├── monitoring.py        # Trigger/view continuous monitoring runs & diffs
│   │   └── pharmacies.py        # GET /v1/pharmacies/nearby (verified + stock status)
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models (see Data Model below)
│   │   └── session.py
│   ├── acquisition/             # Forked & extended searchify modules
│   │   ├── search/
│   │   └── extract/
│   ├── intelligence/
│   │   ├── llm_client.py        # Provider-agnostic structured LLM wrapper
│   │   ├── extractor.py         # Unstructured page/PDF -> structured drug record
│   │   ├── discovery.py         # Multi-query product discovery pipeline
│   │   └── monitor.py           # Periodic re-crawl, hashing, change/recall detection
│   ├── validation/
│   │   ├── evidence.py          # Verbatim quote + numeric claim gate
│   │   ├── trust.py             # Domain trust tiers & promotion rules
│   │   └── versioning.py        # Diffing & packaging version management
│   ├── verification/
│   │   ├── engine.py            # Multi-layer verification orchestrator + scoring
│   │   ├── signals/
│   │   │   ├── nafdac.py        # NAFDAC registry lookup + format/status check
│   │   │   ├── barcode.py       # GTIN check-digit + product match
│   │   │   ├── batch.py         # Batch/expiry/spec consistency checks
│   │   │   └── visual.py        # CV model client + MockCVAdapter
│   └── pharmacies/
│       └── service.py           # Nearby verified pharmacy + confirmed inventory lookup
├── scripts/
│   └── seed_demo.py             # Seeds realistic Nigerian drugs, versions, NAFDAC & pharmacies
└── tests/
```

---

## 4. Product Intelligence Database (Core Schema)

1. **`products`** — Canonical drug record (`id`, `brand_name`, `generic_name`, `active_ingredients`, `strength`, `dosage_form`, `manufacturer`, `status`: `staging` | `approved` | `recalled`).
2. **`product_versions`** — Historical packaging/spec revisions (`id`, `product_id`, `version_label`, `gtins`, `packaging_description`, `reference_images` [URLs + perceptual/SHA hashes], `effective_from`, `effective_to`, `is_current`, `status`: `unverified` | `approved`).
3. **`regulatory_records`** — Cached/mirrored NAFDAC records (`nafdac_number`, `product_name`, `manufacturer`, `registration_status`: `active` | `expired` | `revoked`, `expiry_date`, `last_synced_at`, `raw_source_url`).
4. **`sources` & `evidence_claims`** — Provenance layer (`url`, `domain`, `trust_tier` [1=Regulatory/Official Manufacturer, 2=Vetted Pharma/Distributor, 3=General Web], `field_name`, `extracted_value`, `verbatim_quote`, `verified_numbers`, `status`, `last_checked_at`).
5. **`verification_runs`** — Audit log of every Genium check (`id`, `submitted_payload`, `matched_product_id`, `matched_version_id`, `signal_results` JSON, `verdict`, `confidence`, `created_at`).
6. **`pharmacies` & `pharmacy_inventory`** — Strictly separated tables:
   - `pharmacies`: `id`, `name`, `license_id`, `address`, `lat`, `lng`, `verification_status` (`verified` | `pending` | `suspended`).
   - `pharmacy_inventory`: `pharmacy_id`, `product_id`, `availability_status` (`confirmed` | `unconfirmed` | `out_of_stock`), `confirmed_at`, `confirmation_source`.
7. **`jobs`** — Async tracking for `discovery` and `monitoring` runs (`id`, `job_type`, `target`, `status`, `result_summary`, `error`).

---

## 5. External Contracts (Lock Early)

### A. Genie ↔ CV Model (`POST {CV_SERVICE_URL}/analyze`)
- **Genie sends:** `scan_image_url` (or base64), `candidate_versions` (each with `version_id` + `reference_image_urls`).
- **CV returns:** `best_match_version_id`, `similarity_score` (0–1), `confidence` (0–1), `anomalies` (list of `{region, description, severity}`), `ocr_extracted` (`product_name`, `nafdac_number`, `batch_number`, `expiry_date`, `gtin`), `model_version`.
- *Built with a `MockCVAdapter` first so Genie works end-to-end immediately.*

### B. Genie ↔ Genium (`POST /v1/verify`)
- **Genium sends:** `image_url` (optional), `barcode_gtin` (optional), `nafdac_number` (optional), `batch_number` (optional), `expiry_date` (optional), `product_name_hint` (optional), `user_location` (`lat`, `lng`, optional).
- **Genie returns:**
  - `verdict`: `authentic` | `likely_authentic` | `suspicious` | `likely_counterfeit` | `unknown`
  - `confidence`: `0.0–1.0`
  - `matched_product` + `matched_version` (including whether it matched a **historical** valid version)
  - `signals`: per-layer breakdown (`visual`, `nafdac`, `barcode`, `batch_consistency`, `version_match`)
  - `discovery_job_id`: populated when product is unknown so Genium can poll async investigation
  - `safer_alternatives`: nearby verified pharmacies (explicitly tagging `pharmacy_verified` vs. `stock_confirmed`) when verdict is `suspicious` or `likely_counterfeit`

---

## 6. Phased Build Plan

### Phase 1 — Foundation, Schema & Contracts
- [ ] Initialize Python project (`pyproject.toml`, `FastAPI`, `SQLAlchemy`, `Alembic`, `pytest`, `ruff`).
- [ ] Implement the core DB models and initial migration.
- [ ] Define Pydantic request/response schemas for **Genie ↔ Genium** and **Genie ↔ CV Model**, plus `MockCVAdapter`.
- [ ] Wire up `/health` and skeleton `/v1/*` routes so Genium & CV teams can inspect live OpenAPI docs immediately.

### Phase 2 — Forked Acquisition Layer (Search + Extract)
- [ ] Port lean `searchify` modules (`search/`, `extract/`) without `rerank`.
- [ ] Extend `extract/structured.py` to extract `Product.image`, `og:image`, packaging `<img>` candidates, `manufacturer`, and NAFDAC number patterns.
- [ ] Add unit tests with saved HTML/PDF fixtures (offline, deterministic).

### Phase 3 — Product Intelligence, Discovery & Source Validation
- [ ] Build `intelligence/llm_client.py` + `extractor.py` (JSON-LD first → Cloud LLM structured extraction for missing fields).
- [ ] Build `validation/evidence.py` (verbatim quote check + numeric claim check) and `validation/trust.py` (domain trust tiers + staging → approved promotion rules).
- [ ] Build `intelligence/discovery.py`: given a drug name, NAFDAC number, or GTIN, runs multi-query discovery across manufacturer/regulatory/pharma sources, validates evidence, and writes staged records + reference images to the DB.

### Phase 4 — Multi-Layer Verification Engine & Versioning
- [ ] Implement individual verification signals:
  - `nafdac.py`: format validation + local registry lookup + cross-check product/manufacturer match.
  - `barcode.py`: GTIN check-digit validation + DB match.
  - `batch.py`: expiry date sanity, batch format, and cross-field consistency.
  - `visual.py`: calls CV adapter (or `MockCVAdapter`) against current + historical `product_versions`.
- [ ] Implement asymmetric weighted scoring in `verification/engine.py` (e.g., invalid/mismatched NAFDAC or severe visual anomaly heavily penalizes score; valid barcode alone is never enough).
- [ ] Wire unknown-product fallback to enqueue an async `discovery` job and return `discovery_job_id`.

### Phase 5 — Continuous Data Monitoring
- [ ] Build `intelligence/monitor.py`: re-fetches tracked product sources & regulatory pages, compares content/JSON-LD/image hashes against stored snapshots, and runs live quote checks.
- [ ] Detect packaging/spec changes → create a new staged `product_version` (never overwrite historical versions) and surface alerts for recalls/revoked NAFDAC numbers.

### Phase 6 — Verified Pharmacy Discovery
- [ ] Implement `pharmacies/service.py` + `GET /v1/pharmacies/nearby` (distance calculation, filter by `verified` pharmacies, optional `product_id` join against `pharmacy_inventory`).
- [ ] Enforce the schema/API distinction: `pharmacy_verified: true` is always returned separately from `stock_confirmed: true | false`.
- [ ] Integrate `safer_alternatives` into `/v1/verify` when a scan is flagged as suspicious/counterfeit.

### Phase 7 — Hackathon Readiness & Demo Kit
- [ ] Build `scripts/seed_demo.py` with 10–15 well-known Nigerian pharmaceuticals (e.g., Coartem, Augmentin, Emzor Paracetamol, Lonart, Panadol, etc.), including at least 2 products with **multiple historical packaging versions**, valid/expired NAFDAC records, and verified pharmacies with confirmed vs. unconfirmed stock.
- [ ] End-to-end integration tests covering: genuine scan, historical packaging scan (no false positive), counterfeit/mismatched NAFDAC scan (triggers nearby verified pharmacies), and unknown product scan (triggers live discovery).
- [ ] Add `docker-compose.yml` + concise `README.md` for one-command startup during the hackathon.
