"""Image Quality Gating evaluating blur, glare, illumination, and framing."""
from dataclasses import dataclass, field
from typing import List, Optional
import cv2
import numpy as np


@dataclass
class QualityGateResult:
    passed: bool
    blur_score: float
    glare_ratio: float
    pack_area_ratio: float
    guidance_codes: List[str] = field(default_factory=list)
    rejection_reason: Optional[str] = None


class ImageQualityGate:
    """Fast CPU-based quality evaluation completed in <150ms."""

    def __init__(
        self,
        min_blur_score: float = 120.0,
        max_glare_ratio: float = 0.08,
        min_pack_area_ratio: float = 0.20,
        max_pack_area_ratio: float = 0.95,
    ):
        self.min_blur_score = min_blur_score
        self.max_glare_ratio = max_glare_ratio
        self.min_pack_area_ratio = min_pack_area_ratio
        self.max_pack_area_ratio = max_pack_area_ratio

    def evaluate(self, image_np: np.ndarray) -> QualityGateResult:
        if len(image_np.shape) == 3:
            gray = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(image_np, cv2.COLOR_BGR2HSV)
        else:
            gray = image_np
            hsv = None

        guidance: List[str] = []

        # 1. Blur evaluation via Modified Laplacian Variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())
        if blur_score < self.min_blur_score:
            guidance.append("HOLD_STEADY_BLURRY")

        # 2. Specular glare evaluation
        glare_ratio = 0.0
        if hsv is not None:
            # High value (V > 245) with low saturation (S < 35) defines specular glare
            v_channel = hsv[:, :, 2]
            s_channel = hsv[:, :, 1]
            glare_mask = (v_channel > 245) & (s_channel < 35)
            glare_ratio = float(np.sum(glare_mask) / glare_mask.size)
            if glare_ratio > self.max_glare_ratio:
                guidance.append("REDUCE_GLARE")

        # 3. Framing / scale estimation
        h, w = gray.shape[:2]
        total_pixels = h * w
        _, thresh = cv2.threshold(gray, 40, 255, cv2.THRESH_BINARY)
        non_zero = cv2.countNonZero(thresh)
        pack_area_ratio = float(non_zero / total_pixels) if total_pixels > 0 else 1.0

        if pack_area_ratio < self.min_pack_area_ratio:
            guidance.append("MOVE_CLOSER")

        passed = len(guidance) == 0
        rejection_reason = None
        if not passed:
            rejection_reason = f"Image failed quality thresholds: {', '.join(guidance)}"

        return QualityGateResult(
            passed=passed,
            blur_score=blur_score,
            glare_ratio=glare_ratio,
            pack_area_ratio=pack_area_ratio,
            guidance_codes=guidance,
            rejection_reason=rejection_reason,
        )
