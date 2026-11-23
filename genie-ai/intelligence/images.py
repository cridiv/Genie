"""SSRF-safe candidate image download, dimension filter, and SHA-256 + dHash deduplication."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from discovery.models import DiscoveryBundle
from scraper.extract import egress

_SOURCE_PRIORITY = {"jsonld": 0, "image_search": 1, "og": 2, "img": 3}
_USER_AGENT = "Mozilla/5.0 (compatible; GenieAI/0.1)"


@dataclass
class DownloadedImage:
    url: str
    source_page_url: str
    source_trust_tier: int
    extraction_source: str
    alt: str
    mime_type: str
    width: int
    height: int
    sha256: str
    dhash: str
    raw_bytes: bytes


def compute_dhash(img: Image.Image) -> str:
    """Compute a 64-bit perceptual difference hash (16-char hex) using Pillow only."""
    gray = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(
        gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
    )
    bits = 0
    bit_idx = 0
    for row in range(8):
        offset = row * 9
        for col in range(8):
            if pixels[offset + col] > pixels[offset + col + 1]:
                bits |= 1 << bit_idx
            bit_idx += 1
    return f"{bits:016x}"


def hamming_distance(h1: str, h2: str) -> int:
    """Bitwise Hamming distance between two hex dHash fingerprints."""
    return (int(h1, 16) ^ int(h2, 16)).bit_count()


def collect_candidate_image_urls(
    bundle: DiscoveryBundle,
    max_candidates: int = 16,
) -> List[Dict]:
    """Collect and rank candidate image URLs from scraped sources and direct image search."""
    ranked: List[tuple[tuple[int, int, int], Dict]] = []
    seq = 0
    for source in bundle.sources:
        for img in source.images:
            url = str(img.get("url") or "").strip()
            if not url:
                continue
            ext_src = str(img.get("source") or "img")
            sort_key = (source.trust_tier, _SOURCE_PRIORITY.get(ext_src, 4), seq)
            seq += 1
            ranked.append(
                (
                    sort_key,
                    {
                        "url": url,
                        "source_page_url": source.url,
                        "source_trust_tier": source.trust_tier,
                        "extraction_source": ext_src,
                        "alt": str(img.get("alt") or ""),
                        "declared_width": img.get("width"),
                        "declared_height": img.get("height"),
                    },
                )
            )

    for img in getattr(bundle, "image_candidates", None) or []:
        url = str(img.get("url") or "").strip()
        if not url:
            continue
        ext_src = str(img.get("source") or "image_search")
        tier = int(img.get("source_trust_tier") or 3)
        sort_key = (tier, _SOURCE_PRIORITY.get(ext_src, 1), seq)
        seq += 1
        ranked.append(
            (
                sort_key,
                {
                    "url": url,
                    "source_page_url": str(img.get("source_page_url") or ""),
                    "source_trust_tier": tier,
                    "extraction_source": ext_src,
                    "alt": str(img.get("alt") or img.get("title") or ""),
                    "declared_width": img.get("width"),
                    "declared_height": img.get("height"),
                },
            )
        )

    ranked.sort(key=lambda pair: pair[0])
    out: List[Dict] = []
    seen_urls: set[str] = set()
    for _key, item in ranked:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        out.append(item)
        if len(out) >= max_candidates:
            break
    return out


class _DownloadRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _safe_http_download(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
) -> Tuple[bytes, str]:
    current_url = url
    with httpx.Client(follow_redirects=False, timeout=timeout, headers={"User-Agent": _USER_AGENT}) as client:
        for _hop in range(4):
            parsed = urlparse(current_url)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
                raise _DownloadRejected("invalid_url")
            if not egress._resolve(parsed.hostname):
                raise _DownloadRejected("address_blocked")

            with client.stream("GET", current_url) as resp:
                if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                    current_url = urljoin(current_url, resp.headers["location"])
                    continue
                if not (200 <= resp.status_code < 300):
                    raise _DownloadRejected(f"http_{resp.status_code}")

                content_type = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if content_type and not content_type.startswith("image/"):
                    raise _DownloadRejected("not_image")

                content_len = resp.headers.get("content-length")
                if content_len and content_len.isdigit() and int(content_len) > max_bytes:
                    raise _DownloadRejected("too_large")

                chunks: List[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise _DownloadRejected("too_large")
                    chunks.append(chunk)
                return b"".join(chunks), content_type

    raise _DownloadRejected("too_many_redirects")


def download_and_deduplicate_images(
    candidates: List[Dict],
    *,
    max_unique: int = 6,
    min_dim: int = 250,
    max_aspect: float = 3.5,
    dhash_threshold: int = 6,
    max_bytes: int = 5_000_000,
    timeout: float = 12.0,
    downloader: Optional[Callable[[str], Tuple[bytes, str]]] = None,
) -> Tuple[List[DownloadedImage], List[Dict]]:
    """Download candidate images, drop tiny/banner/corrupt files, and deduplicate by SHA-256 + dHash."""
    kept: List[DownloadedImage] = []
    rejected: List[Dict] = []
    seen_sha: set[str] = set()
    seen_dhash: List[str] = []

    for cand in candidates:
        if len(kept) >= max_unique:
            break
        url = str(cand.get("url") or "")
        try:
            if downloader is not None:
                raw_bytes, header_ct = downloader(url)
            else:
                raw_bytes, header_ct = _safe_http_download(url, timeout=timeout, max_bytes=max_bytes)
        except _DownloadRejected as exc:
            rejected.append({"url": url, "reason": exc.reason})
            continue
        except (httpx.HTTPError, OSError, ValueError) as exc:
            rejected.append({"url": url, "reason": f"download_error: {type(exc).__name__}"})
            continue

        if not raw_bytes:
            rejected.append({"url": url, "reason": "empty_image"})
            continue

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.load()
                width, height = img.size
                pil_fmt = img.format
                dhash = compute_dhash(img)
        except (UnidentifiedImageError, OSError, ValueError):
            rejected.append({"url": url, "reason": "invalid_image"})
            continue

        if width < min_dim or height < min_dim:
            rejected.append({"url": url, "reason": "too_small", "width": width, "height": height})
            continue

        aspect = max(width / height, height / width)
        if aspect > max_aspect:
            rejected.append({"url": url, "reason": "banner_aspect", "width": width, "height": height})
            continue

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        if sha256 in seen_sha:
            rejected.append({"url": url, "reason": "duplicate_sha256"})
            continue

        if any(hamming_distance(dhash, prev) <= dhash_threshold for prev in seen_dhash):
            rejected.append({"url": url, "reason": "duplicate_dhash"})
            continue

        mime = (
            Image.MIME.get(pil_fmt or "")
            or (header_ct.split(";", 1)[0].strip().lower() if header_ct else "")
            or "image/jpeg"
        )
        seen_sha.add(sha256)
        seen_dhash.append(dhash)
        kept.append(
            DownloadedImage(
                url=url,
                source_page_url=str(cand.get("source_page_url") or ""),
                source_trust_tier=int(cand.get("source_trust_tier") or 3),
                extraction_source=str(cand.get("extraction_source") or "img"),
                alt=str(cand.get("alt") or ""),
                mime_type=mime,
                width=width,
                height=height,
                sha256=sha256,
                dhash=dhash,
                raw_bytes=raw_bytes,
            )
        )

    return kept, rejected
