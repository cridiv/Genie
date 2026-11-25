# GENIE AI — Part 1: Product Intelligence, Data Grounding & Reference Curation

> **Purpose:** Hackathon technical walkthrough of `genie-ai/` — what we started with, why each component was built, how it works under the hood, and exact file/function references so you can answer deep technical questions with confidence.

---

## 1. The Starting Point & Core Problem

### What We Started With
At the beginning, counterfeit drug detection in Nigeria had two broken extremes:
1. **Manual NAFDAC number lookup** — counterfeiters copy real NAFDAC registration numbers onto fake boxes, so checking "does `04-1928` exist?" is trivially defeated.
2. **Naive "ask an LLM if this photo is real"** — LLMs hallucinate GTINs, batch numbers, and shelf lives, have no ground-truth Nigerian packaging photos, and cannot reliably tell a genuine 2022 edition from a 2025 redesign or a counterfeit.

### What We Built to Solve It
**GENIE AI** (`genie-ai/`) is a **Product Intelligence & Grounded Verification Engine** backed by:
- A local mirror of all **9,065 NAFDAC Greenbook drug registrations** (SQLite + FTS5 WAL).
- A **curated allowlist of 53 trusted pharmaceutical sources** (20 verified Nigerian licensed retail pharmacies, 21 official manufacturers, 7 regulators, 5 provisional).
- A **multi-angle web discovery & SmPC extraction pipeline** with a deterministic **Evidence Gate** that rejects ungrounded LLM claims and quarantines hallucinated numbers.
- A **human-approved reference image pipeline** (`staging` → `approved`) so Computer Vision never trains or compares against scraped counterfeit news photos.

---

## 2. Layer-by-Layer Breakdown (`genie-ai/`)

### Layer A — Local NAFDAC Greenbook Registry (`registry/greenbook.py`)
- **Why we built it:** Live scraping `greenbook.nafdac.gov.ng` during a consumer scan is slow (seconds) and fragile. We needed sub-5ms authoritative Tier 1 lookups for every registered drug in Nigeria.
- **What it does:**
  - Stores **9,065 NAFDAC-registered products** in `genie-ai/data/greenbook.db` with SQLite **WAL mode** (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA busy_timeout=5000`) for concurrent reads/writes and **FTS5 full-text search**.
  - Normalizes NAFDAC numbers (`04-1928`, `A4-4238`, `C4-0143`), active ingredients, strength, dosage form, pack size, applicant/manufacturer, and registration status.
  - **Key real-world discovery:** Across all 9,065 rows, Greenbook only has two status strings: `'Active'` (6,277) and `'Inactive'` (2,788 — including legitimate household drugs like Coartem `04-3275`, Lonart `A4-4238`, and Panadol Extra `04-0005` awaiting renewal). We engineered our downstream verifier to **never** falsely flag `'Inactive'` as counterfeit.
- **Exact files & functions:**
  - `genie-ai/registry/greenbook.py`: `GreenbookStore`, `lookup_by_nafdac()`, `search()`, `upsert_records()`, `normalize_nafdac_number()`.
  - `genie-ai/scripts/sync_greenbook.py`: pulls and updates the local mirror from NAFDAC Greenbook.

---

### Layer B — Curated Trusted Sources Allowlist (`registry/trusted_sources.py` & `discovery/trust.py`)
- **What we started with:** Open-web search and image search initially returned seized counterfeit photos from Nigerian news blogs (`realnewsmagazine.net/...IMG-20260924-WA0048.jpg`) and foreign B2B export listings (`indiamart.com`, `alibaba.com`).
- **Why we built it:** A counterfeit detector that accidentally saves a seized fake box as its "authentic reference" is worse than useless. Every source must be trust-tiered before its text or images enter a dossier.
- **What it does:**
  - `TrustedSourceStore` (`genie-ai/data/genie.db`, table `trusted_sources`, WAL mode) seeds idempotently with **53 sources (48 verified, 5 provisional)**:
    - **20 verified Nigerian licensed retail pharmacies** (e.g. `healthplusnigeria.com`, `medplusnigeria.com`, `drugstoc.com`, `alphapharmacy.com.ng`, `mophethonline.com`, `h-medix.com`, `kunlearapharmacy.ng`, etc.).
    - **21 official manufacturers** (`gsk.com`, `novartis.com`, `emzorpharma.com`, `fidson.com`, `haleon.com`, etc.).
    - **7 regulators & official SmPC repositories** (`nafdac.gov.ng`, `medicines.org.uk` / eMC, `ema.europa.eu`, `who.int`, etc.).
    - **5 provisional aggregators** (`gomed.ng`, `onehealthng.com`, `medecify.com`, etc. — blocked from auto-entering reference images).
  - `is_disqualified_image_source()` blocks news/press sites, WhatsApp image URLs (`WA00...`), counterfeit/seizure/recall alert pages, and B2B marketplaces (`BLOCKED_DOMAINS`: `indiamart.com`, `alibaba.com`, `made-in-china.com`, `tradeindia.com`).
- **Exact files & functions:**
  - `genie-ai/registry/trusted_sources.py`: `TrustedSourceStore`, `ensure_seeded()`, `get_verified_image_domains()`, `lookup_domain()`.
  - `genie-ai/discovery/trust.py`: `classify_url()`, `is_disqualified_image_source()`, `BLOCKED_DOMAINS`, `rank_and_select_sources()`.

---

### Layer C — Multi-Angle Discovery Pipeline (`discovery/` & `scraper/`)
- **Why we built it:** When a consumer scans a drug that isn't cached yet (Level C — e.g. Kesartem `C4-0143` or Ibumartem `B4-6458`), GENIE AI needs to autonomously gather authoritative regulatory alerts, SmPC/leaflet specs, Nigerian pharmacy product pages, and packaging images in the background.
- **What it does:**
  1. **Seed Enrichment (`enrich_seed_from_greenbook`)**: fills missing brand name, strength, manufacturer, or NAFDAC number from local `greenbook.db`.
  2. **Multi-Angle Query Planning (`build_queries`)**: generates 5 targeted angles:
     - `regulatory_alerts` (`site:nafdac.gov.ng` for recalls/counterfeit Public Alerts)
     - `manufacturer` (official SmPC / patient leaflet / packaging)
     - `pharma_reference` (Nigerian pharmacy product pages with loose strength matching so `20mg + 120mg` matches `20/120`)
     - `packaging_alerts` (new pack / counterfeit notices in Nigeria)
     - `identifier_exact` (exact NAFDAC number or GTIN lookup)
  3. **Trusted Image & Pharmacy Queries (`build_trusted_image_queries`, `build_trusted_pharmacy_web_queries`)**: strips dosage/form to core brand (`_brand_only_term`), adds negative exclusions (`-dispersible`, `-syrup`) when mismatched, and chunks `site:` queries across verified Nigerian pharmacies (5 domains/query).
  4. **Scraper & Structured Extractor (`scraper/`)**: fetches HTML/PDFs, extracts JSON-LD (`Drug`/`Product` schemas), validates GTIN-8/12/13/14 check digits, extracts NAFDAC numbers without confusing dates, and cleans article text via `trafilatura`.
- **Exact files & functions:**
  - `genie-ai/discovery/planner.py`: `enrich_seed_from_greenbook()`, `build_queries()`, `build_trusted_image_queries()`, `build_trusted_pharmacy_web_queries()`, `_brand_only_term()`, `_image_exclusions()`.
  - `genie-ai/discovery/runner.py`: `discover()`, `_run_image_discovery()`.
  - `genie-ai/scraper/search/_common.py`: `site_scoped()` (multi-domain OR grouping).
  - `genie-ai/scraper/extract/reader.py`, `structured.py`, `identifiers.py`: HTML/PDF extraction + GTIN/NAFDAC parsing.

---

### Layer D — LLM Product Intelligence Synthesizer & Evidence Gate (`intelligence/` & `validation/`)
- **What we started with:** A basic LLM prompt returning JSON with no guarantee that numbers (`gtins`, `shelf_life_months`, `affected_batches`) actually came from the scraped documents, and Gemini 503/504 timeouts during live demos.
- **Why we built it:** In healthcare, a hallucinated shelf life or invented recall batch can misclassify a real drug as fake (or vice versa). We needed resilient multimodal LLM providers + deterministic grounding checks.
- **What it does:**
  1. **Swappable Cloud LLM Providers (`intelligence/llm.py`)**:
     - `NvidiaProvider` (auto-selected when `NVIDIA_API_KEY` is set): calls NVIDIA NIM (`nvidia/nemotron-3.5-lightning-30b-a3b` for text + `nvidia/nemotron-3.5-super-vl-120b-a12b` for vision with automatic fallbacks).
     - `GeminiProvider`: `google-genai` SDK with 90s timeout, `ThinkingLevel.LOW`, and automatic fallback on `404`/`429`/`500`/`503`/`504`.
  2. **SmPC Section Extraction (`extract_smpc_key_sections`, `parse_shelf_life_months`)**: Before truncating long SmPC PDFs (e.g., eMC UK leaflets), extracts **§3 Pharmaceutical Form**, **§6.3 Shelf Life**, **§6.4 Storage**, and **§6.5 Nature and Contents of Container** so critical verification specs are never cut off.
  3. **Rich Dossier Schema (`intelligence/schemas.py`)**: `CandidateProductDossier` holds `gtins`, `shelf_life_months`, `storage_statement`, `expected_security_features` (`SecurityFeatureSpec`), `known_counterfeit_tells` (`CounterfeitTell` tagged as `nafdac_derived` vs `independent`), `packaging_versions` (supporting current + historical valid editions), `reference_level` (`A`/`B`/`C`), and `dossier_status` (`staging`/`approved`).
  4. **Deterministic Evidence Gate (`validation/evidence.py`)**:
     - Runs inside `synthesize_dossier()` before saving `product.json`.
     - **Verbatim Quote Check**: normalizes smart quotes/dashes/whitespace and verifies every `EvidenceClaim.verbatim_quote` actually appears in its cited source text.
     - **Numeric Quarantine**: automatically strips/quarantines any LLM-extracted `gtins`, `shelf_life_months`, or `affected_batches` not grounded in the source bundle or failing GTIN check-digit math.
     - **Tier 1 Conflict Detection**: blocks auto-promotion to `approved` if an LLM claim contradicts the authoritative NAFDAC Greenbook record.
- **Exact files & functions:**
  - `genie-ai/intelligence/llm.py`: `LLMProvider`, `NvidiaProvider`, `GeminiProvider`, `get_default_provider()`.
  - `genie-ai/intelligence/schemas.py`: `CandidateProductDossier`, `SecurityFeatureSpec`, `CounterfeitTell`, `EvidenceClaim`, `PackagingVersion`.
  - `genie-ai/intelligence/synthesizer.py`: `synthesize_dossier()`, `extract_smpc_key_sections()`, `parse_shelf_life_months()`, `collect_validated_gtins()`, `compute_reference_level()`, `_normalize_counterfeit_tells()`.
  - `genie-ai/validation/evidence.py`: `validate_and_gate_dossier()`, `EvidenceGateReport`.

---

### Layer E — Curated Reference Image Pipeline (`intelligence/images.py`, `scripts/ingest_references.py`, `scripts/promote_reference.py`)
- **Why we built it:** Automated web image scraping alone has too much risk of polluting ground truth with foreign export packs or seized counterfeit photos. Judges love seeing a **human-in-the-loop curation gate** for safety-critical CV ground truth.
- **What it does:**
  - **Reference Levels (`compute_reference_level`)** — counts **only `approved`** images:
    - **Level A:** Multi-angle approved photos (`front_box` + `back_box`/`blister`) with local regulatory markers.
    - **Level B:** At least 1 approved real packaging photo (our 5 demo products are all **Level B**: `augmentin_625_mg`, `coartem_20_120_tablets`, `emzor_paracetamol_dispersible_tablet`, `lonart_dispersible_tablets`, `panadol_extra_caplet`).
    - **Level C:** Zero approved images (Greenbook-only — graceful degradation applies).
  - **3-Step Review Workflow (`scripts/ingest_references.py`)**:
    1. `--fetch-review`: downloads candidate images into `data/review_images/<slug>/` + `manifest.json` without touching `product.json`.
    2. Human reviewer visually inspects the folder and deletes any wrong/bad images.
    3. `--ingest-review --approve-by <name>`: computes SHA-256 + 64-bit dHash, dedups, saves clean files into `data/products/<slug>/images/`, updates `product.json` with `status: "approved"`, `approved_by`, and recomputes `reference_level`.
- **Exact files & functions:**
  - `genie-ai/intelligence/images.py`: `collect_candidate_images()`, `LocalImageStorage`.
  - `genie-ai/scripts/ingest_references.py`: `fetch_review_images()`, `ingest_review_folder()`.
  - `genie-ai/scripts/promote_reference.py`: promotes individual staged images to `approved`.
