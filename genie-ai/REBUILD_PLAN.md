# GENIE AI — From-Scratch Build Plan

## Phase 1: Project Setup & Dependencies
1. Initialize Python 3.11+ package structure (`pyproject.toml`, `requirements.txt`, `.gitignore`, `.env` template).
2. Configure environment variables (`NVIDIA_API_KEY`, `GEMINI_API_KEY`, `SERPER_API_KEY`, `GENIE_LLM_PROVIDER`).

## Phase 2: Local Regulatory & Trust Registries (`registry/`)
3. Build `registry/greenbook.py` — SQLite WAL + FTS5 store for NAFDAC Greenbook records (`lookup_by_nafdac`, `search`, `upsert_records`, NAFDAC number normalization).
4. Build `scripts/sync_greenbook.py` — paginated sync script to populate `data/greenbook.db` (9,065 NAFDAC products).
5. Build `registry/trusted_sources.py` — SQLite WAL `trusted_sources` table in `data/genie.db` seeded with verified Nigerian licensed pharmacies, official manufacturers, regulators, and provisional domains.

## Phase 3: Web Search & Document Extraction Layer (`scraper/`)
6. Build `scraper/config.py`, `scraper/limits.py`, `scraper/reasons.py` — settings, rate/size limits, and error codes.
7. Build `scraper/search/` — unified search backends (`duckduckgo.py`, `searxng.py`, `cloud.py` for Serper web/news/images + Tavily fallback, `_common.py` with `site_scoped` and deduping, `regions.py`).
8. Build `scraper/extract/` — HTTP fetching (`pages.py`, `stealth.py`, `egress.py`, `netlimits.py`), HTML cleaning (`htmltext.py`, `reader.py`), PDF text extraction (`pdf.py`), and structured pharma extractors (`structured.py`: JSON-LD Drug/Product, GTIN check-digit validation, NAFDAC regex extraction, image ranking).

## Phase 4: Multi-Angle Product Discovery (`discovery/`)
9. Build `discovery/models.py` — `DiscoverySeed`, `SearchQuery`, `DiscoveredSource`, `DiscoveryBundle`.
10. Build `discovery/trust.py` — domain trust tiering (Tiers 0–4), `BLOCKED_DOMAINS` (B2B marketplaces), `is_disqualified_image_source` (blocks news/WhatsApp/counterfeit seizure photos), URL canonicalization, and source ranking/diversity selection.
11. Build `discovery/planner.py` — Greenbook seed enrichment, 5-angle web query builder, brand-only `site:`-scoped trusted image queries, and trusted pharmacy page queries with dosage-form exclusions.
12. Build `discovery/runner.py` — orchestrate Greenbook lookup + web search + page/PDF fetch + trusted image search into a `DiscoveryBundle`.

## Phase 5: Product Intelligence, Vision & Evidence Gate (`intelligence/` & `validation/`)
13. Build `intelligence/schemas.py` — Pydantic v2 schemas (`CandidateProductDossier`, `PackagingVersion`, `ReferenceImageRecord`, `SecurityFeatureSpec`, `CounterfeitTell`, `EvidenceClaim`, list/scalar coercion validators).
14. Build `intelligence/llm.py` — swappable structured + vision `LLMProvider` (`NvidiaProvider` + `GeminiProvider` with model fallback chains and JSON cleanup).
15. Build `intelligence/storage.py` — local image storage (`LocalImageStorage`) with SHA-256 and 64-bit dHash computation.
16. Build `intelligence/images.py` — trusted-only candidate image downloader, vision inspection filters, deterministic pack/watermark/dispenser gates, and image funnel metrics.
17. Build `validation/evidence.py` — deterministic Evidence Gate (verbatim quote verification, numeric grounding & quarantine of ungrounded `gtins`/`shelf_life_months`/`affected_batches`, Tier 1 Greenbook conflict detection, `staging` → `approved` promotion gate).
18. Build `intelligence/synthesizer.py` — SmPC section extraction (§3, §6.3–6.5), shelf-life parser, GTIN collector, `compute_reference_level` (A/B/C from approved images only), counterfeit-tell tagging (`nafdac_derived` vs `independent`), and end-to-end `synthesize_dossier()`.

## Phase 6: Curated Reference Image Tooling (`scripts/`)
19. Build `scripts/run_discovery.py` — CLI to run end-to-end discovery + synthesis + Evidence Gate and save `data/products/<slug>/product.json`.
20. Build `scripts/ingest_references.py` — 3-step manual review workflow (`--fetch-review` → human inspection → `--ingest-review --approve-by`).
21. Build `scripts/promote_reference.py` — CLI to promote staged reference images to `approved` and recompute `reference_level`.

## Phase 7: Multi-Signal Verification Engine (`verification/`)
22. Build `verification/schemas.py` — `ScanInput`, `VisualMatchInput`, `VisualAnomaly`, `SignalResult`, `CounterfeitTellHit`, `VerificationResult`, and `to_ml_infra_verdict()`.
23. Build the 7 signal evaluators in `verification/signals/`:
    - `visual.py` (`evaluate_visual_signal` + `MockCVAdapter`, Level A/B/C weights, legacy edition support)
    - `nafdac.py` (`evaluate_nafdac_signal`, active/inactive-renewal vs revoked handling)
    - `spec_ocr.py` (`evaluate_spec_ocr_signal`, OCR confidence gate `>= 0.85`)
    - `batch_expiry.py` (`evaluate_batch_expiry_signal`, multi-format blister date parsing + SmPC shelf-life check)
    - `gtin.py` (`evaluate_gtin_signal`, GS1 check digit + dossier GTIN match)
    - `security_features.py` (`evaluate_security_features_signal`, "not observed != absent" rule)
    - `recalls_and_tells.py` (`evaluate_recalls_and_tells_signal`, NAFDAC Public Alert & batch hard-negative gate)
24. Build `verification/engine.py` — product resolver (`_resolve_product` with Greenbook fallback + brand-token guard), coverage-weighted fusion, hard-negative overrides, and `nafdac_derived` vs `independent` verdict ceiling.
25. Build `verification/image_scan.py` & `scripts/verify_image.py` — Vision-LLM photo extraction + reference packaging visual comparator with graceful degradation.
26. Build `verification/adapters/ml_infra_adapter.py` — bidirectional schema bridge (`scan_input_from_ml_infra`, `to_ml_infra_response`, `MLInfraPackComparatorAdapter`).

## Phase 8: Concurrent Orchestrator, Scan Persistence & API (`orchestrator/` & `api/`)
27. Build `orchestrator/jobs.py` — SQLite WAL `JobStore` (`discovery_jobs`) with atomic deduplication + bounded background `DiscoveryJobRunner` (`ThreadPoolExecutor`).
28. Build `orchestrator/scans.py` — SQLite WAL `ScanStore` (`verification_scans`) + JSON artifact writer (`data/scans/<scan_id>.json`) storing `summary`, `limitations`, `counterfeit_tell_hits`, and full payload.
29. Build `orchestrator/service.py` — `GenieOrchestrator` coordinating parallel CV + local verification, non-blocking async discovery, scan persistence, product listing, and health metrics.
30. Build `api/main.py` — FastAPI gateway exposing:
    - `GET /v1/health`
    - `POST /v1/verify`, `POST /v1/verify/image`, `POST /v1/verify/ml-infra`
    - `GET /v1/products`, `GET /v1/products/{slug}`
    - `POST /v1/discovery/jobs`, `GET /v1/jobs`, `GET /v1/jobs/{job_id}`
    - `GET /v1/scans`, `GET /v1/scans/{scan_id}`

## Phase 9: Verification Test Suite (`tests/`)
31. Write unit & integration tests across all layers (`test_greenbook.py`, `test_trusted_sources.py`, `test_structured.py`, `test_discovery.py`, `test_intelligence.py`, `test_ingest_references.py`, `test_verification_engine.py`, `test_hardening.py`, `test_orchestrator.py`, `test_image_scan.py`, `test_ml_infra_integration.py`).

## Phase 10: Containerization & Cloud Deployment
32. Build `genie-ai/Dockerfile`, `genie-ai/.dockerignore`, and root `docker-compose.yml` (wiring `genie-ai:8001` with `ml-infra:8000` and persistent `data/` volumes).
33. Deploy to cloud VM (Nobus FCS), transfer `.env` + `data/greenbook.db` + `data/genie.db` + approved `data/products/`, start stack, and verify live endpoints.
