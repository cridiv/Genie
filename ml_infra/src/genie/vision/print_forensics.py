"""Print forensics: Halftone texture, CIELAB delta-E color, and edge sharpness."""
import cv2
import numpy as np


class PrintForensicsAnalyzer:
    """Inspects packaging print quality and color fidelity."""

    @staticmethod
    def calculate_cielab_delta_e(query_bgr: np.ndarray, ref_bgr: np.ndarray) -> float:
        """Calculates Delta-E color distance in CIELAB space."""
        query_lab = cv2.cvtColor(query_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        ref_lab = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        delta_e = np.sqrt(np.sum((query_lab - ref_lab) ** 2, axis=2))
        return float(np.mean(delta_e))

    @staticmethod
    def edge_sharpness(gray_img: np.ndarray) -> float:
        """Measures high-frequency gradient sharpness across printed edges."""
        gx = cv2.Sobel(gray_img, cv2.CV_32F, 1, 0)
        gy = cv2.Sobel(gray_img, cv2.CV_32F, 0, 1)
        mag = cv2.magnitude(gx, gy)
        return float(np.mean(mag))
