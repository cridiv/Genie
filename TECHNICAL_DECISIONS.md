# GENIE AI — Technical Decisions & Explanations

> A plain-English record of the key engineering decisions behind **GENIE AI**—what we built, why we chose this approach, and how each part works.

---

## Step 1: Upgrading the Scraper for Pharma Data & Visuals

### 1. Why we forked `searchify` into `scraper/` (without `rerank`)

Instead of building a web scraper from scratch or installing a heavy black-box library, we forked the core search and page-extraction modules from `sami-mag07/searchify` (MIT-licensed) into [`scraper/`](scraper/).

- **What we kept:** Web search (`DuckDuckGo`, `SearXNG`, optional `Serper`/`Tavily`), a multi-stage page fetcher (fast HTTP first, escalating to TLS impersonation or a browser only when blocked), SSRF security checks (prevents fetching private/internal addresses), PDF reading, and JSON-LD parsing.
- **What we removed:** The local cross-encoder reranker (`rerank.py`). It requires `sentence-transformers` and loads a ~470 MB model that consumes **1–2 GB of RAM per process**. Since Genie uses a Cloud LLM for reasoning and structured extraction, we don't need that memory overhead.

---

### 2. Structured Pharma Extraction (`schema.org/Product` and `schema.org/Drug`)

#### What is JSON-LD?
Many websites embed a hidden `<script type="application/ld+json">` block inside their HTML to describe the page cleanly for search engines like Google. Reading this block gives us **exact, structured data without needing an AI model to guess from messy page text**.

#### Why we extend it beyond `Product` to `Drug`
- **Online pharmacies and retail stores** usually tag their pages as `"@type": "Product"`, which gives us:
  - `name`, `brand`, `manufacturer`, `sku`, `mpn`, `gtin` (barcode), `image`, `price`, and `availability`.
- **Medical directories and manufacturer portals** often tag their pages as `"@type": "Drug"` instead, which gives us pharma-specific fields that `Product` doesn't have:
  - `activeIngredient` (e.g., *Amoxicillin / Clavulanic Acid*)
  - `dosageForm` (e.g., *Film-coated tablet*)
  - `nonProprietaryName` (the generic drug name)
  - `manufacturer`, `image`, and `description`

By supporting **both** `Product` and `Drug` in `scraper/extract/structured.py`, we pull clean pharmaceutical data for free whenever a website provides it.

---

### 3. Regulatory & Barcode Pre-Extraction (NAFDAC + GTIN)

Before sending any text to an AI model, the scraper scans the page text for high-value identifiers using fast, deterministic rules:

- **NAFDAC Registration Numbers:** Matches standard Nigerian regulatory formats (e.g., `A4-1234`, `B4-5678`, `04-1234`, `01-5678`), prioritizing matches that appear near the word `"NAFDAC"`.
- **Barcodes (GTIN / EAN / UPC):** Looks for 8-, 12-, 13-, or 14-digit codes and validates them using the **GS1 check-digit formula** (a quick math check built into every real barcode). This prevents the scraper from mistaking phone numbers, dates, or order IDs for barcodes.

---

### 4. Extracting Candidate Product Images (Avoiding Junk)

A typical web page has 30–50 `<img>` tags—most of them are logos, payment icons, banners, avatars, or "related products" thumbnails.

Instead of grabbing every image on a page, the scraper collects a **priority-ranked, filtered list** (capped at ~5–8 candidates per page):

1. **Priority 1 (Best signal):** `image` directly from JSON-LD `Product` or `Drug` metadata.
2. **Priority 2:** Social preview tags (`og:image`, `twitter:image`).
3. **Priority 3 (Fallback):** `<img>` tags inside the main content area only (ignoring `<header>`, `<nav>`, `<footer>`, and `<aside>`), automatically skipping:
   - Vector icons (`.svg`, `.ico`) and inline `data:` URIs
   - Tiny images (width or height `< 150px`)
   - URLs or `alt` text containing junk words (`logo`, `icon`, `banner`, `badge`, `avatar`, `sprite`, `payment`, `placeholder`)

Each candidate is returned with its absolute URL and lightweight context (`source`, `alt`, `width`, `height`).

---

### 5. Deduplicating Images with `SHA-256` & Perceptual Hashing (`pHash`)

When Genie searches 6–8 websites for a single drug (e.g., *Augmentin 625mg*), it may collect 25+ image URLs. In practice, many of those are the **exact same manufacturer stock photo** re-uploaded by different pharmacies.

We deduplicate them in two layers:

- **Exact Hash (`SHA-256`):**
  - Checks if two files are **byte-for-byte identical**.
  - *Limitation:* If Pharmacy A hosts `augmentin.jpg` at `800×800` and Pharmacy B hosts the **same photo** resized to `600×600` or converted to `.webp`, their `SHA-256` hashes are completely different.

- **Perceptual Hash (`pHash` / `dHash`):**
  - Shrinks the image to a tiny grayscale grid (e.g., `8×8`), looks at the overall visual structure (light vs. dark regions), and turns it into a compact **64-bit visual fingerprint** (e.g., `f3a1c04b9e22d108`).
  - **Same photo, resized or compressed:** The two fingerprints differ by only **0–5 bits** → **Duplicate! Drop it.**
  - **Different photo** (e.g., back of the box, blister pack, or a **new packaging redesign**): The fingerprints differ by **20+ bits** → **Distinct image! Keep it.**
  - **Why it's great:** Runs in **< 1 millisecond** on CPU using lightweight libraries (`Pillow` + `imagehash`), with virtually zero RAM and no ML model needed. During Continuous Monitoring, a brand-new `pHash` on an official manufacturer page is also a fast early signal of a packaging change.

---

### 6. "How Do We Know What We're Seeing?" (Image Verification)

HTML rules only tell us *where* an image sat on a page—not what is actually drawn inside it. A website might still set its company logo as `og:image`, use a generic stock photo of pills, or show *Augmentin 375mg* on a page discussing *Augmentin 625mg*.

We solve this with a **2-step verification funnel**:

1. **Deterministic Pre-Filter (Zero AI cost):**
   - Download the candidate images, drop tiny files (`< 250px`), drop extreme banner shapes (e.g., `width / height > 3.5` is almost always a site banner, not a medicine box), and deduplicate with `SHA-256` + `pHash`.
   - This reduces 25+ raw URLs down to **3–6 unique candidate images**.

2. **Multimodal Cloud LLM Check (Runs *once* per discovered product, never on live user scans):**
   - Send those 3–6 unique candidates in a **single multimodal LLM call** alongside the target product details (e.g., *"Augmentin 625mg, GSK, 14 tablets"*) and ask for structured JSON per image:
     - `is_product_packaging`: `true / false` *(rejects logos, stock photos, lifestyle ads)*
     - `matches_target_product`: `true / false` *(reads the text printed on the box—rejects `375mg` when we need `625mg`)*
     - `view_type`: `front_box` | `back_box` | `blister_pack` | `bottle` | `leaflet` | `other`
     - `packaging_cues`: colors, logo placement, holographic seal, visible dosage or NAFDAC number
     - `quality_ok`: `true / false` *(rejects blurry or heavily watermarked images)*

This costs fractions of a cent per newly discovered product, requires zero local GPU/RAM, and ensures only **clean, verified, angle-tagged packaging photos** enter our Product Intelligence Database.

---

### 7. How We Store Images (and Why Genie Does *Not* Store Its Own Vectors)

Because **Genie** and the **Computer Vision (CV) model** are separate components with separate owners, keeping a clean boundary is critical:

- **Why Genie does NOT generate image vectors:**
  - Image vectors (embeddings) are tied to the specific vision model that created them. If Genie generated embeddings with one model (e.g., CLIP) and the CV team used another (e.g., DINOv2, ResNet, or a fine-tuned packaging model), those vectors would live in incompatible math spaces and be useless to the CV model.

- **What Genie DOES store:**
  1. **Actual image binaries** in object storage (S3 / Cloudflare R2 / Supabase Storage, or a local `./data/images/` folder during the hackathon). We never rely on hotlinking external pharmacy URLs because external links frequently break or block requests.
  2. **Structured metadata in the database (`reference_images` table):**
     - `id`, `product_version_id`
     - `storage_path` / `public_url`
     - `source_url` & `source_trust_tier` *(where the image came from)*
     - `sha256` & `phash` *(deduplication & change detection)*
     - `width`, `height`, `view_type`, `status` (`staging` | `approved`)
  3. **Curated Reference Set cap:** Only **3–6 distinct, verified images** are kept per `product_version` (e.g., front, back, blister pack), prioritized by source trust tier.

- **How Genie hands images to the CV model:**
  - **Pull (at verification time):** Genie passes the 3–6 `reference_image_urls` for the candidate product version(s) to the CV service.
  - **Push (at approval time, optional):** Whenever Genie approves a new reference image, it notifies the CV service (`POST /cv/index`) so the CV model can generate and store its *own* vectors in its own index.

**Summary of ownership:** Genie owns the *curated, verified, versioned reference images*; the CV model owns *visual embeddings and similarity scoring*.

---

## Step 2: NAFDAC Greenbook SQLite Mirror + Multi-Angle Discovery & Trust Tiering

### 1. Why we mirror the NAFDAC Greenbook into a local SQLite database (`registry/`)

Looking up `greenbook.nafdac.gov.ng` live on every scan or discovery run would be slow and fragile if the government portal lags or goes down during a demo. Instead, we pull the entire NAFDAC Greenbook registry (~9,000+ registered drug records) into a local **SQLite + FTS5 (Full-Text Search)** file (`data/greenbook.db`) via its JSON DataTables endpoint.

**Why splitting NAFDAC into two layers works best:**
1. **Local Greenbook Mirror (fast, static baseline):**
   - Answers exact NAFDAC number lookups (`04-1234`, `A4-100160`) and fuzzy brand/ingredient/applicant searches in **milliseconds**, even completely offline.
   - **Enriches weak hints before web search starts:** If a user only scans `"Artheget EZ"`, local Greenbook immediately hands Genie the exact NAFDAC number (`A4-6238`), strength (`80 mg; 480 mg`), active ingredients (`Artemether; Lumefantrine`), applicant/manufacturer (`Getz Pharma Nigeria Limited`), and even a **direct link to the official NAFDAC SmPC PDF** (Summary of Product Characteristics).
2. **Live NAFDAC Alert Search (fresh warnings):**
   - Official counterfeit alerts, batch recalls, and safety warnings are published *after* registration. Keeping a live targeted search for NAFDAC alerts/recalls catches fresh warnings that a static registry might still show as `Active`.

---

### 2. Parallel Multi-Angle Search (`discovery/planner.py`, `discovery/runner.py`)

A single search query like `"Coartem"` returns mostly generic encyclopedia pages or random online stores. Instead, Genie takes the Greenbook-enriched seed and fires up to **5 targeted search angles in parallel**, then merges everything into **one unified `DiscoveryBundle`**:

1. **`regulatory_alerts`** — Looks on `nafdac.gov.ng` for recall notices, counterfeit alerts, or safety circulars.
2. **`manufacturer`** — Looks for official manufacturer pages, packaging details, and PDF leaflets (SmPC).
3. **`pharma_reference`** — Targets clinical drug databases and licensed Nigerian pharmacies for ingredients, pack sizes, and clean reference photos.
4. **`packaging_alerts`** — Searches broadly for `"new pack"`, packaging changes, or fake-product warnings in Nigeria.
5. **`identifier_exact`** *(when a NAFDAC code or GTIN barcode is known)* — Searches the exact code to uncover distributor sheets and alerts.

- **Rate-limit awareness:** Keyless DuckDuckGo throttles bursts if 5 requests hit at the exact same millisecond, so Genie defaults to 2 workers with a light `0.3s` stagger on DuckDuckGo, and scales up to 4 concurrent workers with `0s` stagger when SearXNG or Serper is configured.
- **Official SmPC PDF inclusion:** If Greenbook gives us an official `smpc_url` PDF, Genie automatically adds it as a Tier 1 regulatory document so `scraper` extracts its text alongside the web pages.

---

### 3. What `discovery/trust.py` does (Cleanup, Blocklist, and Trust Tiers)

Web search returns messy, duplicate, and sometimes dangerous links. `trust.py` handles three critical filters before Genie scrapes or trusts anything:

1. **URL Canonicalization (No double-counting):**
   - Strips `www.`, `#fragments`, trailing slashes, and tracking parameters (`?utm_source=...`, `fbclid`, `gclid`).
   - *Why:* Prevents Genie from scraping the exact same page twice under two tracking URLs—or mistakenly thinking two independent sources corroborated a fact when both URLs pointed to the same page.

2. **Counterfeit-Risk Blocklist (`BLOCKED_DOMAINS`):**
   - Drops classifieds and social platforms (`jiji.ng`, `aliexpress.com`, `temu.com`, `facebook.com`, `instagram.com`, `tiktok.com`, `reddit.com`, `quora.com`, etc.) **before fetching**.
   - *Why:* Counterfeit sellers frequently post fake boxes on open marketplaces and social media. Blocking them protects our Product Intelligence Database and CV reference image pool from being poisoned.

3. **Domain Trust Tiers (Who we scrape first & who we believe later):**
   - **Tier 1 (`regulatory` & `official_manufacturer`):** `nafdac.gov.ng`, `who.int`, `fda.gov`, `ema.europa.eu`, `medicines.org.uk`, plus known pharma manufacturers (`gsk.com`, `novartis.com`, `emzor.com`, `fidson.com`, `getzpharma.com`, etc.) and dynamic matching on distinctive manufacturer name tokens (ignoring generic words like `"pharma"` or `"limited"` so `"Getz Pharma Nigeria Limited"` matches `getzpharma.com` without matching random `*pharma.com` domains).
   - **Tier 2 (`vetted_pharma`):** Clinical databases (`drugs.com`, `dailymed.nlm.nih.gov`, `emdexonline.com`) and established Nigerian pharmacies (`medplusnigeria.com`, `healthplusnigeria.com`, `drugstoc.com`, etc.).
   - **Tier 3 (`general_web`):** News sites, health blogs, and unverified stores. Helpful for catching recall news or leads, but never trusted on its own without corroboration.

When selecting the top ~8 URLs to scrape, Genie ranks **Tier 1 > Tier 2 > Tier 3**, adds a bonus if multiple search angles found the same URL, caps **max 2 URLs per domain**, and guarantees representation across search angles so one noisy domain can't crowd out other evidence.

---

## Step 3: Dossier Synthesis & Visual Verification (`intelligence/`)

### 1. Pure-Pillow `dHash` instead of heavy image-hashing packages
To deduplicate near-identical packaging photos across pharmacies (e.g., the same photo resized from `800×800` to `500×500` or recompressed as `.webp`), we compute a **64-bit difference hash (`dHash`)** directly in pure `Pillow` (`intelligence/images.py`):
- Shrinks the image to a `9×8` grayscale grid and checks whether each pixel is brighter than the pixel to its right, producing a compact 16-character hex fingerprint.
- **Why we avoided `imagehash`/`numpy`/`scipy`:** Installing those just for a 64-bit hash adds ~150 MB of heavy math libraries. Pure Pillow runs in `< 1 ms` with zero extra dependencies.

---

### 2. Two-Stage Image Verification Funnel
1. **SSRF-safe download + deterministic pre-filter (`intelligence/images.py`):**
   - Validates every URL against private/internal IP blocks (`scraper.extract.egress._resolve`, including redirect hops), caps download size (`5 MB`), verifies valid image bytes with `Pillow`, drops tiny thumbnails (`< 250px`) and wide banner shapes (`aspect ratio > 3.5`), and deduplicates via exact `SHA-256` and `dHash` Hamming distance (`<= 6`).
2. **Single-call Multimodal Gemini Verification (`intelligence/synthesizer.py`):**
   - Sends the remaining top candidates (up to 6 unique images) in **one multimodal Gemini request** alongside the target drug metadata.
   - Gemini returns strict JSON (`BatchImageVerificationResponse`) classifying `is_product_packaging`, `matches_target_product` (catches wrong strength/brand boxes), `view_type` (`front_box`, `back_box`, `blister_pack`, `bottle`, `leaflet`), `visible_cues`, `visible_text_snippets`, and `quality_ok`.

---

### 3. Local Disk Image Storage behind a Swappable Interface (`intelligence/storage.py`)
- Verified images are saved under `data/images/<product_key>/<sha256[:16]><ext>` via `LocalImageStorage`.
- It implements a minimal `ImageStorage` protocol (`save`, `exists`, `read`), so swapping local disk for S3 / Cloudflare R2 / Supabase Storage later takes one adapter class without touching the pipeline.
- Still **no Genie-side image vectors**: Genie stores curated, angle-tagged reference binaries and hands them to the CV service when needed.

---

### 4. Structured Gemini Dossier Extraction with Mandatory Provenance (`intelligence/llm.py`, `schemas.py`)
- Wired to **Gemini (`google-genai`, defaulting to `gemini-2.5-flash`)** behind a minimal `LLMProvider` protocol so OpenAI or Anthropic can be swapped cleanly.
- Uses strict Pydantic `response_schema` (`ExtractedDossierResponse`) so every extracted drug/packaging field comes with an `EvidenceClaim` (`{field_name, value, source_url, verbatim_quote}`).
- This creates the exact contract **Step 4** needs to deterministically verify every quote and number against the original scraped pages before any dossier leaves `staging`.
