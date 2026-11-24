"""Online verification pipeline orchestrator executing all branches within <4s."""
import base64
from pathlib import Path
import time
from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from genie.barcode.decode import MultiDecoder
from genie.common.exceptions import QualityGateError
from genie.db.models import ReferenceImage
from genie.schemas.scan import ScanRequest
from genie.schemas.verdict import VerificationResponse, VerdictState
from genie.storage.vector_store import VectorStore
from genie.verification.explain import ExplainabilityEngine
from genie.verification.fusion import CalibratedFusionEngine
from genie.verification.resolver import ProductResolver
from genie.verification.signals.barcode_signal import BarcodeSignalEvaluator
from genie.verification.signals.batch_signal import BatchSignalEvaluator
from genie.verification.signals.history_signal import HistorySignalEvaluator
from genie.verification.signals.nafdac_signal import NAFDACSignalEvaluator
from genie.verification.signals.visual_signal import VisualSignalEvaluator
from genie.vision.anomaly import PatchCoreAnomalyDetector
from genie.vision.embed import VisualEmbedder
from genie.vision.ocr import PackagingOCR
from genie.vision.pack_compare import PackComparator
from genie.vision.pack_detect import PackDetectorRectifier
from genie.vision.quality import ImageQualityGate
from genie.vision.vlm_review import VLMReviewer


class VerificationPipeline:
    def __init__(
        self,
        db_session: AsyncSession,
        vector_store: VectorStore,
        enable_vlm_review: bool = False,
    ):
        self.db = db_session
        self.vector_store = vector_store
        self.enable_vlm_review = enable_vlm_review

        # Components
        self.quality_gate = ImageQualityGate()
        self.pack_rectifier = PackDetectorRectifier()
        self.visual_embedder = VisualEmbedder()
        self.ocr = PackagingOCR(enable_vlm=False)
        self.anomaly_detector = PatchCoreAnomalyDetector()
        self.pack_comparator = PackComparator()
        self.vlm_reviewer = VLMReviewer()
        self.resolver = ProductResolver(db_session, vector_store)
        self.fusion = CalibratedFusionEngine()

        # Signal evaluators
        self.barcode_eval = BarcodeSignalEvaluator()
        self.nafdac_eval = NAFDACSignalEvaluator()
        self.batch_eval = BatchSignalEvaluator()
        self.visual_eval = VisualSignalEvaluator()
        self.history_eval = HistorySignalEvaluator()

    async def _load_reference_image(
        self, version_id: Any
    ) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]]]:
        """Loads canonical reference image and semantic element regions for a product version."""
        stmt = (
            select(ReferenceImage)
            .filter(ReferenceImage.product_version_id == version_id)
            .order_by(ReferenceImage.trust_tier.asc(), ReferenceImage.created_at.desc())
        )
        res = await self.db.execute(stmt)
        ref_record = res.scalars().first()
        if not ref_record or not ref_record.storage_path:
            return None, None

        ref_path = Path(ref_record.storage_path)
        if not ref_path.is_file():
            return None, ref_record.semantic_regions

        ref_img = cv2.imread(str(ref_path), cv2.IMREAD_COLOR)
        return ref_img, ref_record.semantic_regions

    async def verify_scan(self, request: ScanRequest) -> VerificationResponse:
        t0 = time.perf_counter()

        # 1. Parse Image
        first_img = request.images[0]
        if first_img.image_bytes_base64:
            img_bytes = base64.b64decode(first_img.image_bytes_base64)
            img_np = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        else:
            # Synthetic 512x512 placeholder if bytes not sent
            img_np = np.zeros((512, 512, 3), dtype=np.uint8)

        # 2. Quality Gate (<150ms)
        q_res = self.quality_gate.evaluate(img_np)
        if not q_res.passed:
            raise QualityGateError(
                code="POOR_IMAGE_QUALITY",
                message=q_res.rejection_reason or "Image failed quality gate",
                details={"guidance_codes": q_res.guidance_codes},
            )

        # 3. Pack Rectification
        rect_res = self.pack_rectifier.rectify(img_np)
        rectified_pack = rect_res.rectified_image

        # 4. Barcode Branch
        barcode_res = MultiDecoder.decode(rectified_pack)
        if not barcode_res and request.manual_gtin:
            barcode_res = {"gtin": request.manual_gtin, "check_digit_valid": True}
        gtin = barcode_res.get("gtin") if barcode_res else request.manual_gtin

        # 5. OCR Branch
        ocr_data = self.ocr.extract_text(rectified_pack)
        nafdac = ocr_data.nafdac_number or request.manual_nafdac

        # 6. Visual Embedding
        embedding = self.visual_embedder.embed_image(rectified_pack)

        # 7. Candidate Resolution
        resolved = await self.resolver.resolve(gtin=gtin, nafdac_number=nafdac, embedding=embedding)

        # 7b. Reference Pack Comparison (Color, Element Positioning, Layout, Anomaly)
        ref_img: Optional[np.ndarray] = None
        inlier_ratio = 0.5
        anomaly_score = 0.2
        color_score: Optional[float] = None
        layout_score: Optional[float] = None
        visual_inconsistencies: list[str] = []

        if resolved:
            ref_img, semantic_regions = await self._load_reference_image(resolved.matched_version.id)
            if ref_img is not None:
                comp = self.pack_comparator.compare(
                    query_img=rectified_pack,
                    reference_img=ref_img,
                    semantic_regions=semantic_regions,
                )
                if not comp.alignment_matched and rect_res.homography_matrix is not None:
                    comp_raw = self.pack_comparator.compare(
                        query_img=img_np,
                        reference_img=ref_img,
                        semantic_regions=semantic_regions,
                    )
                    if comp_raw.inlier_ratio > comp.inlier_ratio:
                        comp = comp_raw
                inlier_ratio = comp.inlier_ratio
                anomaly_score = comp.anomaly_score
                color_score = comp.color_score
                layout_score = comp.layout_score
                visual_inconsistencies = comp.inconsistencies

        # 8. Compute Signals
        registered_nafdac_dict = None
        if resolved:
            registered_nafdac_dict = {
                "brand_name": resolved.product.brand_name,
                "manufacturer": resolved.product.manufacturer,
                "status": "active",
            }

        sig_barcode = self.barcode_eval.evaluate(
            barcode_res,
            resolved_product_gtins=resolved.product.gtin_list if resolved else None,
        )
        sig_nafdac = self.nafdac_eval.evaluate(nafdac, registered_nafdac_dict)
        sig_batch = self.batch_eval.evaluate(
            barcode_batch=barcode_res.get("batch") if barcode_res else None,
            barcode_expiry=barcode_res.get("expiry") if barcode_res else None,
            ocr_batch=ocr_data.batch_number,
            ocr_expiry=ocr_data.expiry_date,
        )
        sig_visual = self.visual_eval.evaluate(
            retrieval_cosine_sim=resolved.confidence if resolved else 0.5,
            alignment_inlier_ratio=inlier_ratio,
            patch_anomaly_score=anomaly_score,
            color_score=color_score,
            layout_score=layout_score,
            inconsistencies=visual_inconsistencies,
        )
        sig_history = self.history_eval.evaluate(
            is_legacy_match=resolved.is_legacy_version if resolved else False,
            version_label=resolved.active_version.version_label if resolved else None,
        )

        signals_dict = {
            "barcode": sig_barcode,
            "nafdac": sig_nafdac,
            "batch": sig_batch,
            "visual": sig_visual,
            "history": sig_history,
        }

        # 9. Calibrated Fusion
        verdict, confidence, breakdown, reasons = self.fusion.fuse(signals_dict)

        # 9b. VLM Second-Opinion Triage Review (never sole decider)
        if self.enable_vlm_review and verdict in (VerdictState.SUSPICIOUS, VerdictState.CANNOT_VERIFY):
            try:
                vlm_review = await self.vlm_reviewer.review_packaging_async(
                    rectified_pack, reference_image=ref_img
                )
                if vlm_review and vlm_review.discrepancies:
                    reasons.extend(vlm_review.discrepancies)
            except Exception:
                pass

        # 10. Explanation Assembly
        explanation = ExplainabilityEngine.assemble_explanation(
            verdict=verdict,
            product_name=resolved.product.brand_name if resolved else None,
            version_label=resolved.active_version.version_label if resolved else None,
            is_legacy=resolved.is_legacy_version if resolved else False,
            reasons=reasons,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return VerificationResponse(
            verdict=verdict,
            confidence=confidence,
            matched_product_name=resolved.product.brand_name if resolved else None,
            matched_version_label=resolved.active_version.version_label if resolved else None,
            is_legacy_version=resolved.is_legacy_version if resolved else False,
            explanation=explanation,
            signals=breakdown,
            execution_time_ms=elapsed_ms,
        )
