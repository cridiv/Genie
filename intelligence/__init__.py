"""GENIE AI Dossier Synthesis & Visual Verification layer (Step 3)."""
from __future__ import annotations

from .images import (
    DownloadedImage,
    collect_candidate_image_urls,
    compute_dhash,
    download_and_deduplicate_images,
    hamming_distance,
)
from .llm import DEFAULT_GEMINI_MODEL, GeminiProvider, LLMProvider, get_default_provider
from .schemas import (
    BatchImageVerificationResponse,
    CandidateProductDossier,
    EvidenceClaim,
    ExtractedDossierResponse,
    RawImageCheck,
    VerifiedReferenceImage,
)
from .storage import ImageStorage, LocalImageStorage, default_image_dir
from .synthesizer import (
    build_dossier_prompt,
    build_image_verify_prompt,
    synthesize_dossier,
    verify_images,
)

__all__ = [
    "BatchImageVerificationResponse",
    "CandidateProductDossier",
    "DEFAULT_GEMINI_MODEL",
    "DownloadedImage",
    "EvidenceClaim",
    "ExtractedDossierResponse",
    "GeminiProvider",
    "ImageStorage",
    "LLMProvider",
    "LocalImageStorage",
    "RawImageCheck",
    "VerifiedReferenceImage",
    "build_dossier_prompt",
    "build_image_verify_prompt",
    "collect_candidate_image_urls",
    "compute_dhash",
    "default_image_dir",
    "download_and_deduplicate_images",
    "get_default_provider",
    "hamming_distance",
    "synthesize_dossier",
    "verify_images",
]
