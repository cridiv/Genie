# GENIE AI — Engineering & Database Change Log (`logs.md`)

> **Permanent audit log for GENIE AI ML Infrastructure (`/ml_infra`).**
> **Policy:** All repository milestones, architectural modifications, and **any changes to database schemas, models, or migrations** must be recorded in this document chronologically.

---

## Database Change Protocol & Guidelines

For any future change affecting the database (`src/genie/db/models.py`, Alembic migrations, or table definitions):
1. **Log Entry Required:** Append a new entry under [Database Changelog](#2-database-changelog) before merging or deploying.
2. **Mandatory Fields:**
   - **Timestamp (UTC)**
   - **Change Title & Purpose**
   - **Target Table(s) & Schema Impact**
   - **Migration File / Version ID**
   - **SQL Diff / Model Changes**
   - **Backward Compatibility & Rollback Strategy**

---

## 1. Repository & ML Infrastructure Changelog

### [2026-11-24] Phase 3 Implementation Complete: Text Detection, Recognition & Regulatory OCR Parsing
- **Author:** Genie AI Core Team
- **Scope:** Complete implementation and verification of Phase 3 from `checklist.md`:
  - `src/genie/vision/ocr.py`:
    - Packaging text-line candidate localization using directional morphological Sobel gradients and horizontal rectangular closing, isolating text strips in $< 30\text{ms}$.
    - Dot-matrix inkjet batch code enhancement via elliptical structuring elements (`3x3`) and CLAHE contrast equalization.
    - Comprehensive regex coverage for Nigerian NAFDAC numbers: Human Medicines (`A4-XXXX`, `B4-XXXX`, `04-XXXX`), Food (`04-XXXX`), Herbal (`04-XXXXL`), and prefixed labels (`NAFDAC REG NO:`, `NRN:`).
    - Batch/Lot, Expiry, and Manufacturing date extraction with contextual keyword matchers.
    - Local Greenbook SQLite FTS5 database lookup in $< 5\text{ms}$.
    - Automated cross-check comparing printed OCR batch/expiry against GS1 barcode payloads to flag counterfeit overprinting.
  - `tests/test_ocr.py`: 6 unit tests covering candidate line detection, dot-matrix enhancement, NAFDAC regexes, batch/expiry parsing, and cross-checks passing (34/34 total tests passing in pytest).
- **Database Schema Changes:** None (no database migrations or model modifications).

### [2026-11-23] Phase 2 Implementation Complete: Barcode Detection, Enhancement & GS1 Parsing
- **Author:** Genie AI Core Team
- **Scope:** Complete implementation and verification of Phase 2 from `checklist.md`:
  - `src/genie/barcode/detect.py`: Gradient edge density detector (Sobel in X direction + morphological closing), cardinal orientation estimator ($0^\circ, 90^\circ, 180^\circ, 270^\circ$), quiet zone padding, YOLO11n barcode session loader, latency $< 40\text{ms}$.
  - `src/genie/barcode/enhance.py`: Auto-deskew across 4 cardinal rotations, CLAHE contrast enhancement (`clipLimit=2.5, tileGridSize=(8,8)`), morphological binarization, Otsu thresholding, unsharp masking, and 2x-4x super-resolution scaling for tiny codes, latency $< 60\text{ms}$.
  - `src/genie/barcode/decode.py`: Multi-decoder ensemble integrating `zxing-cpp`, `pyzbar`, `OpenCV WeChat QR`, `pylibdmtx`, and fallback OCR for human-readable digits, latency $< 150\text{ms}$.
  - `src/genie/barcode/gs1_parser.py`: Unified bracketed and FNC1 stream parsing via `biip` and native fallback, extracting AIs `(01)` GTIN-14, `(10)` Batch, `(17)` Expiry (with `DD=00` month-end handling), `(21)` Serial, GS1 Modulo-10 checksum validation, and Nigeria prefix hint (`615`), latency $< 5\text{ms}$.
  - `src/genie/barcode/digital_link.py`: GS1 Digital Link URI parser, domain whitelist sandboxing, and salt+HMAC cryptographic serial duplicate replay tracking.
  - Test suites: `test_barcode_detect.py`, `test_barcode_decode.py`, `test_gs1_parser.py`, `test_gtin_parser.py` passing across all 28 unit tests.
- **Database Schema Changes:** None (no database migrations or model modifications).

### [2026-11-23] Phase 1 Implementation Complete: Quality Gating & Pack Rectification
- **Author:** Genie AI Core Team
- **Scope:** Complete implementation and verification of Phase 1 from `checklist.md`:
  - `src/genie/vision/quality.py`: Modified Laplacian Variance blur metric, HSV specular glare masking ($V > 245, S < 35, \text{glare} > 8\%$), pack bounding area ratio estimation, real-time guidance codes (`HOLD_STEADY_BLURRY`, `REDUCE_GLARE`, `MOVE_CLOSER`, `SHOW_BACK_PANEL`), latency verification ($< 120\text{ms}$).
  - `src/genie/vision/pack_detect.py`: 4-corner keypoint detection, homography matrix calculation, planar perspective warping to canonical $512\times 512$, cylindrical unrolling algorithm for round syrup bottles/vials ($x' = R \arcsin((x-x_c)/R)$), reprojection error $< 3.0\text{px}$, latency verification ($< 180\text{ms}$).
  - `tests/test_quality_gate.py` & `tests/test_pack_detect.py`: 7 comprehensive unit test suites passing in pytest.
- **Database Schema Changes:** None (no database migrations or model modifications).

### [2026-11-23] Initial Repository Scaffolding (`/ml_infra` Root)
- **Author:** Genie AI Core Team
- **Scope:** Complete initialization and scaffolding of the Machine Learning, Computer Vision, and Verification Infrastructure based on `ML_BUILD_PLAN.md`.

#### Artifacts Created & Configured:
1. **Project & Package Tooling**:
   - `pyproject.toml`: Modern packaging specification using setuptools, dependencies pinned for FastAPI, SQLAlchemy 2.0, ONNX Runtime, OpenCV, Pillow, biip, zxing-cpp, scikit-learn, google-genai. Optional dependency groups: `dev`, `cv-training`, `storage`.
   - `Makefile`: Commands for installation, testing (`pytest`), linting (`ruff`, `mypy`), running API, syncing Greenbook mirror, and indexing vectors.
   - `README.md`: Architecture diagrams, dual-plane workflows, operational concepts, and quickstart documentation.
   - `.env.example`: Template for environment variables (database, Qdrant, S3/R2 storage, Gemini API, paths).
   - `.gitignore`: Configured for Python caches, virtual environments, DVC data directories, ONNX models, and local test artifacts.
   - `alembic.ini`: Database migration configuration configured for `src/genie/db/migrations`.
   - `ML_BUILD_PLAN.md`: Full 19-section engineering design specification for core ML infra.

2. **Configuration Files (`configs/`)**:
   - `configs/sources.yaml`: Source credibility tier registry (Tier 1 Regulatory/Official, Tier 2 Vetted Clinical/Pharmacies, Tier 3 General Web) and high-risk domain blocklist.
   - `configs/thresholds.yaml`: Decision boundaries for antimalarials, antibiotics, analgesics, and FMCG foods, defining quality gate minimums, alignment inlier ratios, and calibrated probability cutoffs.
   - `configs/models.yaml`: Runtime configuration for ONNX models (MobileNetV3 quality gate, YOLO11 pack & barcode detectors, DINOv2 ViT-B/14, PatchCore, PaddleOCR).
   - `configs/fusion_weights.yaml`: Signal weight vectors per category and deterministic hard invalidation rules.

3. **Core ML & Service Modules (`src/genie/`)**:
   - **`common/`**: `config.py` (Pydantic Settings), `logging.py` (structured stdout formatter), `exceptions.py` (domain exceptions: `QualityGateError`, `BarcodeDecodeError`, `RegistryMismatchError`, `ProductNotFoundError`).
   - **`schemas/`**: Pydantic v2 schemas:
     - `product.py`: `ProductBase`, `ProductCreate`, `ProductRead`, `ProductCategory`.
     - `version.py`: `ProductVersionBase`, `ProductVersionCreate`, `ProductVersionRead`, `PackagingSpec`.
     - `evidence.py`: `SourceRecord`, `EvidenceClaim`, `StagedClaim`.
     - `scan.py`: `ScanImage`, `DecodedBarcode`, `OCRExtractedFields`, `ScanRequest`.
     - `verdict.py`: Three-state enum `VerdictState` (`Consistent with genuine`, `Suspicious`, `Cannot verify`), `SignalBreakdown`, `SaferAlternative`, `VerificationResponse`.
   - **`storage/`**:
     - `object_store.py`: Protocol `ImageStorage` and local filesystem implementation `LocalImageStorage`.
     - `vector_store.py`: Protocol `VectorStore` with `VectorSearchResult` and cosine `InMemoryVectorStore`.
   - **`barcode/`**:
     - `gtin.py`: Modulo-10 check digit calculation (`calculate_gs1_check_digit`), validation, GTIN-14 normalization, GS1 prefix hints (Nigeria 615).
     - `gs1_parser.py`: `GS1PayloadParser` extracting AIs `(01)` GTIN, `(10)` Batch, `(17)` Expiry, `(21)` Serial, `(11)` Production date.
     - `digital_link.py`: `parse_digital_link_url` with domain security verification.
     - `enhance.py`: CLAHE contrast enhancement, deskewing, Otsu binarization, and 2x-4x upscaling.
     - `decode.py`: `MultiDecoder` ensemble evaluating `zxing-cpp`, `pyzbar`, and `pylibdmtx`.
     - `detect.py`: `BarcodeDetector` localizing 1D/2D code regions via gradient edge density heuristics.
   - **`vision/`**:
     - `quality.py`: `ImageQualityGate` computing blur Laplacian variance ($\sigma_{\text{Lap}}^2$), specular glare ratio in HSV, framing/scale, with real-time user retake guidance (`MOVE_CLOSER`, `REDUCE_GLARE`, `HOLD_STEADY_BLURRY`).
     - `pack_detect.py`: `PackDetectorRectifier` computing contour keypoints and 4-point planar perspective homography transformation to canonical $512\times 512$ views.
     - `embed.py`: `VisualEmbedder` for extracting normalized 768-dimensional DINOv2 ViT-B/14 embeddings.
     - `match.py`: `GeometricMatcher` evaluating keypoint matching and homography inlier ratios.
     - `anomaly.py`: `PatchCoreAnomalyDetector` computing localized patch differences against genuine memory banks and generating Jet-colormap heatmaps.
     - `ocr.py`: `PackagingOCR` parsing NAFDAC numbers, batch/lot codes, and expiry dates via multi-regex pattern matchers.
     - `print_forensics.py`: `PrintForensicsAnalyzer` calculating CIELAB $\Delta E_{00}$ color distance and high-frequency edge sharpness.
   - **`verification/`**:
     - `signals/`: Modular signal evaluators (`barcode_signal.py`, `nafdac_signal.py`, `batch_signal.py`, `visual_signal.py`, `history_signal.py`).
     - `resolver.py`: `ProductResolver` voting between GTIN, NAFDAC number, and DINOv2 vector candidate matches.
     - `fusion.py`: `CalibratedFusionEngine` enforcing deterministic hard invalidation rules and Platt-scaled weighted scoring.
     - `explain.py`: `ExplainabilityEngine` compiling structured audit reasons into consumer explanations.
     - `pipeline.py`: `VerificationPipeline` orchestrating the full scan-to-verdict lifecycle within <4s latency budget.
   - **`pharmacy/`**:
     - `discovery.py`: `PharmacyDiscoveryService` performing geospatial radius lookups (Haversine distance).
     - `verification.py`: `PharmacyVerificationService` verifying Pharmacists Council of Nigeria (PCN) license status.
     - `inventory.py`: `PharmacyInventoryService` confirming fresh stock availability (<48hr feeds), strictly decoupled from product authenticity.
   - **`api/`**: FastAPI application (`main.py`) with routers for:
     - `POST /v1/verify`: Core mobile verification scan endpoint.
     - `GET /v1/products`: Product intelligence catalogue.
     - `GET /v1/products/{id}/versions`: Version history retrieval (SCD Type 2).
     - `GET /v1/pharmacies/nearby`: Verified pharmacies with stock confirmation flags.
     - `POST /v1/discovery/jobs`: Asynchronous unknown product investigation trigger.
   - **`discovery/` & `extraction/` & `validation/` & `versioning/`**:
     - `discovery/planner.py` & `runner.py`: 5-angle search query planner and executor.
     - `discovery/trust.py`: URL canonicalization, trust tiering, and marketplace blocklist filtering.
     - `extraction/nafdac_parser.py`: Fast local client for SQLite FTS5 NAFDAC Greenbook mirror.
     - `extraction/image_harvester.py`: SSRF-safe image download and 64-bit difference hashing (`dHash`) in Pillow.
     - `extraction/html_clean.py`: Clean text extraction removing scripts, navigation, and boilerplate.
     - `extraction/llm_extractor.py`: Schema-constrained extraction contract with verbatim quote span verification.
     - `validation/source_scoring.py`: Multi-factor evidence scoring formula ($S_{\text{evidence}}$).
     - `validation/staging.py`: Auto-promotion and human review queue criteria.
     - `versioning/diffing.py`: Textual and perceptual spec difference detection.
     - `versioning/lifecycle.py`: SCD Type 2 active, superseded, and retired transition windows.

4. **Training & Evaluation Pipelines**:
   - `training/detection/train_yolo.py`: YOLO fine-tuning script for packaging and barcode localization.
   - `training/embedding/train_metric.py`: DINOv2 metric learning with SupCon loss.
   - `training/anomaly/build_patchcore.py`: PatchCore memory bank construction and coreset subsampling.
   - `training/synthetic/augment_counterfeit.py`: Synthetic adversarial defect and camera degradation generator.
   - `evaluation/barcode_bench/test_barcode_decode.py`: Benchmark suite for barcode and GS1 decoding.

5. **Operational Scripts**:
   - `scripts/sync_greenbook.py`: Ingestion script for official NAFDAC Greenbook DataTables into SQLite FTS5.
   - `scripts/build_vector_index.py`: Batch vector extraction and indexing for approved reference packaging faces.

6. **Infrastructure & Deployment**:
   - `docker/Dockerfile.api`: Container image for FastAPI verification gateway.
   - `docker/Dockerfile.worker`: Container image for background crawler and embedding worker.
   - `docker/docker-compose.yml`: Multi-service compose definition (API, PostgreSQL with pgvector, Qdrant vector engine).
   - `infra/terraform/main.tf`: AWS S3 bucket with 30-day ephemeral lifecycle deletion for unconsented scans.
   - `infra/k8s/deployment.yaml`: Kubernetes Deployment and LoadBalancer Service with health probes.

7. **Test Suites (`tests/`)**:
   - `tests/conftest.py`: Synthetic clean and blurry test fixtures.
   - `tests/test_quality_gate.py`: Verification of Laplacian blur detection and glare rejection.
   - `tests/test_gtin_parser.py`: Verification of GS1 modulo-10 check digits, 14-digit normalization, and Nigeria prefix (615).
   - `tests/test_fusion.py`: Verification of hard invalidation rules, genuine thresholding, and insufficient signal handling.
   - `tests/test_schemas.py`: Pydantic v2 domain model serialization and validation tests.

8. **Virtual Environment**:
   - Created Python 3.11 virtual environment (`.venv`) via `uv` (`uv 0.11.31`).

9. **Phase 4: Visual Feature Embedding, Indexing & Candidate Retrieval [2026-11-24]**:
   - Implemented `src/genie/vision/embed.py` with normalized 768-dim DINOv2 ViT-B/14 feature extraction ($\|v\|_2 = 1.0$), batch inference with dynamic axes, and deterministic spatial-color moment fallback for fast CPU environments ($<70\text{ms}$).
   - Implemented `src/genie/storage/vector_store.py` with `InMemoryVectorStore` supporting top-$k$ cosine similarity search and pre-filtering by GTIN list, NAFDAC number, and lifecycle status ($<25\text{ms}$).
   - Added unit test suite in `tests/test_vector_retrieval.py` verifying unit norm enforcement and pre-filtered candidate retrieval (100% pass).
   - Database schema status: Zero database changes required.

---

## 2. Database Changelog

### [2026-11-23] Initial Database Schema Definition (Baseline v1.0)
- **Author:** Genie AI Core Team
- **Source File:** `src/genie/db/models.py`
- **Engine / Dialect:** SQLAlchemy 2.0 (PostgreSQL 16 with SQLite fallback support)
- **Status:** Baseline Applied

#### Table Definitions & Purpose:

#### 1. `products`
Canonical master product entity for consumable products.
```sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    brand_name VARCHAR(255) NOT NULL,
    generic_name VARCHAR(255),
    manufacturer VARCHAR(255) NOT NULL,
    category VARCHAR(100) DEFAULT 'pharmaceuticals_antimalarials',
    active_ingredients JSON DEFAULT '[]',
    dosage_form VARCHAR(100),
    strength VARCHAR(100),
    primary_nafdac_number VARCHAR(50),
    gtin_list JSON DEFAULT '[]',
    status VARCHAR(50) DEFAULT 'staging',  -- 'staging' | 'approved' | 'recalled'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_products_brand_name ON products (brand_name);
CREATE INDEX ix_products_manufacturer ON products (manufacturer);
CREATE INDEX ix_products_primary_nafdac_number ON products (primary_nafdac_number);
```

#### 2. `product_versions`
Slowly Changing Dimension (SCD Type 2) table storing time-bounded packaging revisions and specs.
```sql
CREATE TABLE product_versions (
    id UUID PRIMARY KEY,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    version_label VARCHAR(255) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,                         -- NULL indicates current active version
    status VARCHAR(50) DEFAULT 'active',   -- 'active' | 'superseded' | 'retired'
    packaging_spec JSON DEFAULT '{}',
    batch_number_regex VARCHAR(255),
    shelf_life_months INTEGER DEFAULT 24,
    evidence_ids JSON DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_product_versions_product_id ON product_versions (product_id);
```

#### 3. `reference_images`
Curated canonical packaging reference imagery per face (front, back, blister, side).
```sql
CREATE TABLE reference_images (
    id UUID PRIMARY KEY,
    product_version_id UUID NOT NULL REFERENCES product_versions(id) ON DELETE CASCADE,
    face_type VARCHAR(50) NOT NULL,        -- 'front' | 'back' | 'blister' | 'side'
    storage_path VARCHAR(500) NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    dhash_64bit VARCHAR(16) NOT NULL,
    semantic_regions JSON DEFAULT '{}',
    quality_grade VARCHAR(10) DEFAULT 'A',
    source_url VARCHAR(500),
    trust_tier INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_reference_images_product_version_id ON reference_images (product_version_id);
CREATE INDEX ix_reference_images_sha256_hash ON reference_images (sha256_hash);
CREATE INDEX ix_reference_images_dhash_64bit ON reference_images (dhash_64bit);
```

#### 4. `evidence_claims`
Provenance and audit trail tying extracted attributes to source URLs and verbatim quotes.
```sql
CREATE TABLE evidence_claims (
    id UUID PRIMARY KEY,
    product_id UUID REFERENCES products(id),
    field_name VARCHAR(100) NOT NULL,
    value TEXT NOT NULL,
    source_url VARCHAR(500) NOT NULL,
    verbatim_quote TEXT NOT NULL,
    verified_in_source BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 5. `scan_records`
Immutable consumer scan verification audit trail storing model versions, extracted fields, and verdicts.
```sql
CREATE TABLE scan_records (
    id UUID PRIMARY KEY,
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_session_hash VARCHAR(64),
    image_storage_path VARCHAR(500),
    decoded_barcode JSON,
    ocr_extracted_fields JSON,
    matched_product_id UUID REFERENCES products(id),
    matched_version_id UUID REFERENCES product_versions(id),
    signal_scores JSON,
    final_verdict VARCHAR(50) NOT NULL,     -- 'Consistent with genuine' | 'Suspicious' | 'Cannot verify'
    calibrated_confidence FLOAT DEFAULT 0.0,
    model_git_commit VARCHAR(40),
    execution_time_ms FLOAT DEFAULT 0.0
);
```

#### 6. `pharmacies`
Directory of verified pharmacies licensed by the Pharmacists Council of Nigeria (PCN).
```sql
CREATE TABLE pharmacies (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    license_id VARCHAR(100) UNIQUE NOT NULL,
    address VARCHAR(500) NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 7. `pharmacy_inventory`
Confirmed stock availability tracking (isolated completely from product authenticity calculation).
```sql
CREATE TABLE pharmacy_inventory (
    id UUID PRIMARY KEY,
    pharmacy_id UUID NOT NULL REFERENCES pharmacies(id),
    product_id UUID NOT NULL REFERENCES products(id),
    availability_status VARCHAR(50) DEFAULT 'unconfirmed', -- 'confirmed' | 'unconfirmed' | 'out_of_stock'
    last_confirmed_at TIMESTAMP
);
```

---
*End of log. Next database schema changes must be recorded directly below.*
