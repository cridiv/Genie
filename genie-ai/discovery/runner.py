"""Multi-angle discovery runner combining local Greenbook, parallel search, and extraction."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional

from registry.greenbook import GreenbookStore, default_db_path
from scraper.config import get_settings
from scraper.extract import extract_report
from scraper.search import SearchBackendError, search_report

from .models import DiscoveredSource, DiscoveryBundle, DiscoverySeed, SearchQuery
from .planner import build_queries, enrich_seed_from_greenbook
from .trust import canonicalize_url, classify_url, extract_domain, rank_and_select


def _lookup_greenbook(
    seed: DiscoverySeed,
    *,
    greenbook: Optional[GreenbookStore],
    db_path: Optional[Path | str],
) -> List[Dict]:
    store = greenbook
    if store is None:
        target_path = Path(db_path) if db_path is not None else default_db_path()
        if not target_path.exists():
            return []
        store = GreenbookStore(target_path)

    matches: List[Dict] = []
    seen_ids: set = set()

    if seed.nafdac_number:
        for row in store.lookup_by_nafdac(seed.nafdac_number):
            pid = row.get("product_id")
            if pid not in seen_ids:
                seen_ids.add(pid)
                matches.append(row)

    if seed.product_name and len(matches) < 5:
        for row in store.search(seed.product_name, manufacturer=seed.manufacturer, limit=5):
            pid = row.get("product_id")
            if pid not in seen_ids:
                seen_ids.add(pid)
                matches.append(row)

    return matches[:5]


def _default_search_settings(
    search_fn: Optional[Callable],
    max_workers: Optional[int],
    stagger_s: Optional[float],
) -> tuple[int, float]:
    if max_workers is not None and stagger_s is not None:
        return max_workers, stagger_s

    if search_fn is not None:
        return (max_workers or 4), (0.0 if stagger_s is None else stagger_s)

    settings = get_settings()
    using_faster_backend = bool(settings.searxng_url or settings.serper_api_key)
    default_workers = 4 if using_faster_backend else 2
    default_stagger = 0.0 if using_faster_backend else 0.3
    return (
        max_workers if max_workers is not None else default_workers,
        stagger_s if stagger_s is not None else default_stagger,
    )


def _run_one_query(
    query_obj: SearchQuery,
    *,
    delay_s: float,
    max_results: int,
    country: Optional[str],
    search_fn: Callable,
) -> tuple[SearchQuery, List[Dict], Optional[Dict]]:
    if delay_s > 0:
        time.sleep(delay_s)
    kwargs: Dict = {"max_results": max_results}
    if query_obj.include_domains:
        kwargs["include_domains"] = query_obj.include_domains
    if query_obj.time_range:
        kwargs["time_range"] = query_obj.time_range
    if country and not query_obj.include_domains:
        kwargs["country"] = country

    try:
        res = search_fn(query_obj.query, **kwargs)
    except SearchBackendError as exc:
        return query_obj, [], {"angle": query_obj.angle, "query": query_obj.query, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return query_obj, [], {
            "angle": query_obj.angle,
            "query": query_obj.query,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if isinstance(res, dict):
        hits = list(res.get("results") or [])
        err = res.get("error")
        err_entry = (
            {"angle": query_obj.angle, "query": query_obj.query, "error": str(err)}
            if err and not hits
            else None
        )
        return query_obj, hits, err_entry

    return query_obj, list(res or []), None


def discover(
    seed: DiscoverySeed,
    *,
    greenbook: Optional[GreenbookStore] = None,
    db_path: Optional[Path | str] = None,
    max_urls: int = 8,
    max_results_per_query: int = 6,
    max_stage: Optional[str] = None,
    budget: Optional[str] = None,
    include_smpc_pdf: bool = True,
    max_workers: Optional[int] = None,
    stagger_s: Optional[float] = None,
    search_fn: Optional[Callable] = None,
    extract_fn: Optional[Callable] = None,
) -> DiscoveryBundle:
    """Run local Greenbook lookup, parallel multi-angle search, trust ranking, and extraction."""
    t0 = time.monotonic()

    # 1. Local Greenbook lookup & seed enrichment
    gb_matches = _lookup_greenbook(seed, greenbook=greenbook, db_path=db_path)
    enriched_seed = enrich_seed_from_greenbook(seed, gb_matches)
    queries = build_queries(enriched_seed)

    # 2. Parallel multi-angle web search
    effective_search = search_fn or search_report
    workers, stagger = _default_search_settings(search_fn, max_workers, stagger_s)

    all_hits: List[Dict] = []
    search_errors: List[Dict] = []
    country = enriched_seed.country.lower() if enriched_seed.country else None

    if queries:
        with ThreadPoolExecutor(max_workers=min(workers, len(queries))) as pool:
            futures = [
                pool.submit(
                    _run_one_query,
                    q,
                    delay_s=idx * stagger,
                    max_results=max_results_per_query,
                    country=country,
                    search_fn=effective_search,
                )
                for idx, q in enumerate(queries)
            ]
            for fut in as_completed(futures):
                q_obj, hits, err_entry = fut.result()
                if err_entry:
                    search_errors.append(err_entry)
                for h in hits:
                    hit_copy = dict(h)
                    hit_copy["angle"] = q_obj.angle
                    all_hits.append(hit_copy)

    # 3. Check if Greenbook top match provides an official SmPC PDF
    smpc_url = ""
    if include_smpc_pdf and gb_matches:
        candidate_smpc = str(gb_matches[0].get("smpc_url") or "").strip()
        if candidate_smpc.startswith(("http://", "https://")):
            smpc_url = candidate_smpc

    web_budget = max(1, max_urls - 1) if smpc_url and max_urls > 1 else max_urls
    selected = rank_and_select(
        all_hits,
        manufacturer_hint=enriched_seed.manufacturer,
        max_urls=web_budget,
        max_per_domain=2,
    )

    # Map canonical URL -> metadata for assembling DiscoveredSource objects after fetch
    meta_by_canon: Dict[str, Dict] = {}
    fetch_urls: List[str] = []

    if smpc_url:
        smpc_canon = canonicalize_url(smpc_url)
        tier, label = classify_url(smpc_url, manufacturer_hint=enriched_seed.manufacturer)
        fetch_urls.append(smpc_url)
        meta_by_canon[smpc_canon or smpc_url] = {
            "url": smpc_url,
            "canonical_url": smpc_canon or smpc_url,
            "domain": extract_domain(smpc_url),
            "trust_tier": tier,
            "trust_label": label,
            "angles": ["greenbook_smpc"],
            "is_smpc_pdf": True,
        }

    for cand in selected:
        if cand.canonical_url in meta_by_canon:
            continue
        fetch_urls.append(cand.url)
        meta_by_canon[cand.canonical_url] = {
            "url": cand.url,
            "canonical_url": cand.canonical_url,
            "domain": cand.domain,
            "trust_tier": cand.trust_tier,
            "trust_label": cand.trust_label,
            "angles": cand.angles,
            "is_smpc_pdf": False,
        }

    # 4. Batch parallel extraction via forked scraper
    extracted_docs: List[Dict] = []
    failed_sources: List[Dict] = []
    if fetch_urls:
        effective_extract = extract_fn or extract_report
        report = effective_extract(
            fetch_urls,
            fmt="text",
            max_stage=max_stage,
            budget=budget,
            structured=True,
        )
        extracted_docs = list(report.get("results") or [])
        failed_sources = list(report.get("failed") or [])

    sources: List[DiscoveredSource] = []
    for doc in extracted_docs:
        doc_url = str(doc.get("url") or "")
        doc_canon = canonicalize_url(doc_url)
        meta = meta_by_canon.get(doc_canon) or meta_by_canon.get(doc_url)
        if meta is None:
            tier, label = classify_url(doc_url, manufacturer_hint=enriched_seed.manufacturer)
            meta = {
                "url": doc_url,
                "canonical_url": doc_canon or doc_url,
                "domain": extract_domain(doc_url),
                "trust_tier": tier,
                "trust_label": label,
                "angles": [],
                "is_smpc_pdf": bool(smpc_url and doc_url == smpc_url),
            }
        sources.append(
            DiscoveredSource(
                url=doc_url or meta["url"],
                canonical_url=meta["canonical_url"],
                domain=meta["domain"],
                trust_tier=meta["trust_tier"],
                trust_label=meta["trust_label"],
                angles=list(meta["angles"]),
                title=str(doc.get("title") or ""),
                content=str(doc.get("content") or ""),
                stage=str(doc.get("stage") or "static"),
                product=doc.get("product"),
                images=list(doc.get("images") or []),
                identifiers=dict(doc.get("identifiers") or {}),
                is_smpc_pdf=bool(meta["is_smpc_pdf"]),
            )
        )

    sources.sort(key=lambda s: (s.trust_tier, not s.is_smpc_pdf))

    stats = {
        "greenbook_match_count": len(gb_matches),
        "queries_executed": len(queries),
        "raw_hits": len(all_hits),
        "urls_selected": len(fetch_urls),
        "pages_extracted": len(sources),
        "pages_failed": len(failed_sources),
        "elapsed_s": round(time.monotonic() - t0, 3),
    }

    return DiscoveryBundle(
        seed=seed,
        enriched_seed=enriched_seed,
        greenbook_matches=gb_matches,
        queries_run=queries,
        search_errors=search_errors,
        sources=sources,
        failed_sources=failed_sources,
        stats=stats,
    )
