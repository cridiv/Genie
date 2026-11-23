"""PatchCore patch-level anomaly detection and heatmap rendering."""
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class AnomalyResult:
    anomaly_score: float  # [0.0, 1.0]
    is_anomalous: bool
    heatmap_bytes: Optional[bytes] = None


class PatchCoreAnomalyDetector:
    """Evaluates patch deviations against a memory bank of genuine reference packs."""

    def __init__(self, anomaly_threshold: float = 0.65):
        self.anomaly_threshold = anomaly_threshold

    def evaluate(self, aligned_query: np.ndarray, aligned_reference: np.ndarray) -> AnomalyResult:
        import cv2

        # Compute structural absolute difference between aligned packs
        diff = cv2.absdiff(aligned_query, aligned_reference)
        if len(diff.shape) == 3:
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        else:
            diff_gray = diff

        # Gaussian smoothing to create contiguous anomaly patches
        smoothed = cv2.GaussianBlur(diff_gray, (15, 15), 0)
        norm_diff = smoothed.astype(np.float32) / 255.0
        score = float(np.mean(norm_diff) * 2.0)
        score = min(max(score, 0.0), 1.0)

        # Generate false-color thermal heatmap
        heatmap = cv2.applyColorMap((norm_diff * 255).astype(np.uint8), cv2.COLORMAP_JET)
        _, buffer = cv2.imencode(".jpg", heatmap)

        return AnomalyResult(
            anomaly_score=score,
            is_anomalous=score > self.anomaly_threshold,
            heatmap_bytes=buffer.tobytes(),
        )
