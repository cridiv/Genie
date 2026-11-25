# GENIE AI & ML Infra — Part 2: Multi-Signal Verification Engine, Orchestrator & Computer Vision Pipeline

> **Purpose:** Deep-dive into how a consumer drug scan is actually verified — both GENIE AI's 7-signal verification engine & concurrent orchestrator (`genie-ai/`) and the dedicated CV/OCR/Barcode/Forensics layer (`ml_infra/`).

---

## 1. GENIE AI Multi-Signal Verification Engine (`genie-ai/verification/`)

### What We Started With
A single binary pass/fail check ("NAFDAC number exists" or "CV score > 0.8") fails in real life:
- What if the drug is newly registered in Greenbook (Level C) with no reference images yet?
- What if the user scanned a genuine older packaging edition that's still within expiry?
- What if the NAFDAC number is valid, the box looks okay, **but** the batch number matches a NAFDAC Public Alert for falsified drugs?

### What We Built
A **coverage-weighted, 7-signal verification engine** with strict anti-false-positive and anti-false-negative safety invariants (`genie-ai/verification/engine.py`).

#### The 7 Signals & Locked Weights
| Signal | File & Function | Source Kind | Max Weight | What It Checks |
| --- | --- | --- | --- | --- |
| **1. Visual Packaging** | `signals/visual.py` (`evaluate_visual_signal`) | `independent` | `0.40` (Level A) / `0.30` (Level B) / `unavailable` (Level C) | Compares scanned pack against approved current **and historical** editions; flags high-severity anomalies without false-alarming valid legacy editions. |
| **2. NAFDAC Registry** | `signals/nafdac.py` (`evaluate_nafdac_signal`) | `nafdac_derived` | `0.20` | Exact match against local 9,065-drug `greenbook.db`. Flags `Revoked`/`Suspended`/`Cancelled` as hard negative, but treats `'Inactive'` / `'Ongoing Renewal'` neutrally so real drugs awaiting renewal aren't falsely called fake. |
| **3. Spec / OCR Consistency** | `signals/spec_ocr.py` (`evaluate_spec_ocr_signal`) | `nafdac_derived` | `0.15` | Gated by `ocr_confidence >= 0.85` (blurry OCR never penalizes). Checks brand, active ingredients, strength, dosage form, and manufacturer printed on the pack against the dossier. |
| **4. Batch & Expiry Validity** | `signals/batch_expiry.py` (`evaluate_batch_expiry_signal`) | `independent` | `0.10` | Parses `MM/YYYY`, `MM/YY`, `DD/MM/YYYY`, `YYYY-MM-DD`, and month-name dates. Flags expired packs, `expiry <= mfg_date`, or `expiry - mfg > shelf_life_months + 2` (impossible shelf life). |
| **5. GTIN / Barcode** | `signals/gtin.py` (`evaluate_gtin_signal`) | `independent` | `0.08` (`not_applicable` if dossier has no GTIN) | Validates GS1 check digit + matches against dossier's grounded `gtins`. Invalid check digit or mismatched GTIN is a hard negative. |
| **6. Security Features** | `signals/security_features.py` (`evaluate_security_features_signal`) | `independent` | `0.07` (`not_applicable` if dossier has none) | Enforces **"not observed != absent"** (a feature not visible from one angle is neutral; only an explicitly checked & missing feature or failed MAS verification is negative). |
| **7. Recalls & Counterfeit Tells** | `signals/recalls_and_tells.py` (`evaluate_recalls_and_tells_signal`) | Safety Gate | `0.00` (Override) | Checks scanned batch/text against NAFDAC Public Alerts & known counterfeit tells (e.g., Augmentin 625mg Batch `562626`, Public Alert No. 42). Triggers `likely_counterfeit` at **any** coverage. |

#### Critical Safety Invariants (Judges Love These)
1. **Hard Negatives Override Everything:** A recalled batch, revoked NAFDAC status, impossible expiry/shelf-life, invalid GTIN check digit, or severe visual counterfeit anomaly triggers `likely_counterfeit` or `suspicious` regardless of how many other signals passed.
2. **Graceful Degradation (Coverage-Based Ceiling):**
   - **Coverage** = `sum(available signal weights) / sum(applicable signal weights)`.
   - If a drug is Level C (no approved images yet), visual weight drops out cleanly; the verdict caps at `registered_unverified` (`Cannot verify`) instead of guessing, and sets `recommend_discovery = True`.
3. **`nafdac_derived` vs `independent` Verdict Ceiling:**
   - Counterfeiters copy real NAFDAC numbers, brand text, and even fake scratch stickers. Therefore, `nafdac_derived` signals, GTIN alone, or an unverified observed sticker **can never** unlock `authentic` or `likely_authentic` — only an `independent` visual match or externally verified security feature (e.g. MAS SMS) can.
4. **6-State Internal Verdict → 3-State Consumer Verdict (`to_ml_infra_verdict`):**
   - `authentic`, `likely_authentic` → **`Consistent with genuine`**
   - `suspicious`, `likely_counterfeit` → **`Suspicious`**
   - `registered_unverified`, `unknown` → **`Cannot verify`**

---

## 2. Concurrent Orchestrator & FastAPI Gateway (`genie-ai/orchestrator/` & `genie-ai/api/`)

### Why We Built It
A consumer scan must respond in **<50ms** (local signals) or **<4s** (with full CV), whereas autonomous web discovery + SmPC synthesis takes **15–45 seconds**. Running discovery synchronously would time out the mobile app.

### How It Works
- **`GenieOrchestrator` (`genie-ai/orchestrator/service.py`)**:
  - Runs the CV adapter (`_cv_pool = ThreadPoolExecutor(max_workers=4)`) **concurrently** with Greenbook pre-warming and local signals.
  - Evaluates all 7 signals via `VerificationEngine.verify()`.
  - If `auto_discover=True` and `result.recommend_discovery=True` (e.g. Level C or unregistered drug), enqueues a **non-blocking background job** and returns the scan verdict immediately (~10–18ms locally).
- **Atomic Deduplicated Job Queue (`genie-ai/orchestrator/jobs.py`)**:
  - `JobStore` persists jobs in SQLite WAL (`genie-ai/data/genie.db`, table `discovery_jobs`).
  - `DiscoveryJobRunner` uses a bounded `ThreadPoolExecutor(max_workers=2)` and atomically deduplicates concurrent scans of the same unknown drug so 50 users scanning Kesartem at once only trigger **1** discovery pipeline run.
- **FastAPI Gateway (`genie-ai/api/main.py`)**:
  - `GET /v1/health` — DB counts (9,065 Greenbook rows, 53 trusted sources, cached products, queue depth).
  - `POST /v1/verify` — structured `ScanInput` verification.
  - `POST /v1/verify/image` — live photo upload using Vision-LLM OCR + visual reference comparison (`verification/image_scan.py`).
  - `POST /v1/verify/ml-infra` — bridge endpoint for `ml_infra`.
  - `GET /v1/products`, `GET /v1/products/{slug}` — inspect cached dossiers.
  - `POST /v1/discovery/jobs`, `GET /v1/jobs`, `GET /v1/jobs/{job_id}` — trigger & poll async discovery.

---

## 3. ML Infrastructure (`ml_infra/src/genie/`)

### Why `ml_infra` Exists Alongside `genie-ai`
While `genie-ai` owns **Product Intelligence, NAFDAC Grounding, Evidence Gating, and Coverage-Weighted Verification**, `ml_infra` owns **heavy Computer Vision, Barcode Decoding, Packaging Forensics, Vector Retrieval, and Verified Pharmacy Discovery** within a `<4s` online scan budget.

### Stage-by-Stage `ml_infra` Online Pipeline (`ml_infra/src/genie/verification/pipeline.py` → `VerificationPipeline.verify_scan()`)

1. **Image Quality Gate (`vision/quality.py` → `ImageQualityGate.evaluate`) — `<120ms` CPU:**
   - Rejects unusable photos *before* wasting compute, returning actionable UI guidance codes:
     - `MOVE_CLOSER` (pack area ratio `< 0.20`)
     - `REDUCE_GLARE` (HSV specular glare `V > 245, S < 35` covering `> 8%` of pack surface)
     - `HOLD_STEADY_BLURRY` (Modified Laplacian Variance `< 120.0`)
2. **Pack Detection & Rectification (`vision/pack_detect.py` → `PackDetectorRectifier.rectify`):**
   - Localizes the carton/blister quadrilateral and applies perspective homography (`cv2.getPerspectiveTransform` / `cv2.warpPerspective`) into a canonical `512x512` planar view (plus cylindrical unwrapping for syrup bottles via `unwrap_cylindrical_surface()`).
3. **Multi-Decoder Barcode Ensemble (`barcode/decode.py` → `MultiDecoder.decode`) — `<150ms`:**
   - Enhances crops (`enhance_barcode_crop`) and cascades across **4 decoders**: `zxing-cpp` → `pyzbar` → OpenCV WeChat QR → `pylibdmtx` (2D GS1 DataMatrix).
   - Parses GS1 Application Identifiers (`gs1_parser.py` → `GS1PayloadParser`) and Digital Link URLs (`digital_link.py`) to extract GTIN-14 (`gtin.py`), batch/lot, expiry, and serial number.
4. **Packaging OCR (`vision/ocr.py` → `PackagingOCR.extract_text`):**
   - Extracts `nafdac_number`, `batch_number`, `expiry_date`, `brand_name`, and `raw_text_lines` into `OCRExtractedFields`.
5. **Visual Embedding & Candidate Resolution (`vision/embed.py`, `verification/resolver.py`, `storage/vector_store.py`):**
   - Embeds the rectified pack (`VisualEmbedder.embed_image`) and resolves candidate product + packaging version via GTIN, NAFDAC number, and Qdrant/vector similarity (`ProductResolver.resolve`).
6. **Forensic Reference-to-Query Pack Comparison (`vision/pack_compare.py` → `PackComparator.compare`):**
   - Compares the rectified query pack against the canonical reference image across **4 forensic dimensions**:
     1. **Geometric Homography Alignment:** ORB keypoints + RANSAC (`GeometricMatcher` in `vision/match.py`) measuring `inlier_ratio` and `reprojection_error`.
     2. **Lighting-Normalized Color Fidelity:** matches CIELAB `L*` luminance (`_normalize_luminance`) so warm/cool room lighting doesn't fool it, then measures `delta_e_ab` and HSV histogram correlation (`color_score`).
     3. **Layout & Critical Element Positioning:** 4×4 grid SSIM (`_compute_ssim`), edge alignment, and anchor-region shift checks (`ElementPositionCheck`: `ok` / `shifted` / `missing_or_altered`).
     4. **Patch Anomaly & Print Forensics:** `PatchCoreAnomalyDetector` (`vision/anomaly.py`) + sharpness ratio (`vision/print_forensics.py`) + visual anomaly heatmap generation.
7. **Reference Pack Indexing (`vision/reference_index.py` → `ReferencePackIndexer.index_reference_pack`):**
   - Canonicalizes genuine reference photos to `512x512`, computes SHA-256 + 64-bit dHash (`compute_dhash_64`), auto-detects salient graphic/text anchor boxes (`extract_salient_regions`), stores metadata in SQL (`ReferenceImage`), and upserts embeddings to `VectorStore`.
8. **Calibrated Local Fusion & VLM Triage (`verification/fusion.py`, `vision/vlm_review.py`):**
   - `CalibratedFusionEngine.fuse()` applies category-specific thresholds (`pharmaceuticals_antimalarials` / `antibiotics`: `genuine >= 0.90`), Platt-scaled sigmoid confidence, and hard-invalidation rules; `VLMReviewer` provides optional second-opinion discrepancy notes (never sole decider).
9. **Verified Pharmacy Discovery (`pharmacy/` & `api/v1/pharmacies.py`):**
   - Surfaces nearby `SaferAlternative` licensed pharmacies with strict separation between `pharmacy_verified` (PCN/licensed status) and `stock_confirmed` (never conflating the two).
